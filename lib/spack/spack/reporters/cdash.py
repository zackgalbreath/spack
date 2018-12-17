# Copyright 2013-2018 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)


import codecs
import cStringIO
import hashlib
import os.path
import platform
import re
import socket
import time
import xml.sax.saxutils
from six import text_type
from six.moves.urllib.request import build_opener, HTTPHandler, Request
from six.moves.urllib.parse import urlencode

import spack.build_environment
import spack.fetch_strategy
import spack.package
from spack.reporter import Reporter
from spack.util.crypto import checksum
from spack.util.log_parse import parse_log_events
import llnl.util.tty as tty

__all__ = ['CDash']

# Mapping Spack phases to the corresponding CTest/CDash phase.
map_phases_to_cdash = {
    'autoreconf': 'configure',
    'cmake':      'configure',
    'configure':  'configure',
    'edit':       'configure',
    'build':      'build',
    'install':    'build'
}

# Initialize data structures common to each phase's report.
cdash_phases = set(map_phases_to_cdash.values())


class CDash(Reporter):
    """Generate reports of spec installations for CDash.

    To use this reporter, pass the ``--cdash-upload-url`` argument to
    ``spack install``::

        spack install --cdash-upload-url=\\
            https://mydomain.com/cdash/submit.php?project=Spack <spec>

    In this example, results will be uploaded to the *Spack* project on the
    CDash instance hosted at https://mydomain.com/cdash.
    """

    def __init__(self, args):
        tty.warn("!!! CDash reporter constructor gets called !!!")
        Reporter.__init__(self, args)
        self.template_dir = os.path.join('reports', 'cdash')
        self.cdash_upload_url = args.cdash_upload_url
        self.install_command = ' '.join(args.package)
        if args.cdash_build:
            self.buildname = args.cdash_build
        else:
            self.buildname = self.install_command
        if args.cdash_site:
            self.site = args.cdash_site
        else:
            self.site = socket.gethostname()
        self.osname = platform.system()
        self.starttime = int(time.time())
        buildstamp_format = "%Y%m%d-%H%M-{0}".format(args.cdash_track)
        self.buildstamp = time.strftime(buildstamp_format,
                                        time.localtime(self.starttime))

    def build_report(self, filename, report_data):
        tty.warn("!!! build_report gets called !!!")
        self.initialize_report(filename, report_data)

        for phase in cdash_phases:
            report_data[phase] = {}
            report_data[phase]['loglines'] = []
            report_data[phase]['status'] = 0
            report_data[phase]['starttime'] = self.starttime
            report_data[phase]['endtime'] = self.starttime

        # Track the phases we perform so we know what reports to create.
        phases_encountered = []

        # Parse output phase-by-phase.
        phase_regexp = re.compile(r"Executing phase: '(.*)'")
        cdash_phase = ''
        tty.warn("!!! parsing build output !!!")

        begin_time = time.clock()
        splitlines_time = 0.0
        find_time = 0.0
        regexp_time = 0.0
        escape_time = 0.0
        append_time = 0.0

        for spec in report_data['specs']:
            for package in spec['packages']:
                if 'stdout' in package:
                    tty.warn("!!! parsing build output for {0} !!!".format(package['name']))
                    before = time.clock()
                    lines = package['stdout'].splitlines()
                    after = time.clock()
                    splitlines_time += (after - before)
                    num_lines = len(lines)
                    tty.warn("!!! it has {0} lines of output !!!".format(num_lines))
                    current_phase = ''
                    for i, line in enumerate(lines):
                        if i % 100 == 0:
                            tty.warn("!!! {0} / {1} complete !!!".format(i, num_lines))
                        match = None
                        before = time.clock()
                        phase_pos = line.find("Executing phase: '")
                        after = time.clock()
                        find_time += (after - before)
                        if phase_pos != -1:
                            before = time.clock()
                            match = phase_regexp.search(line)
                            after = time.clock()
                            regexp_time += (after - before)
                        if match:
                            current_phase = match.group(1)
                            if current_phase not in map_phases_to_cdash:
                                current_phase = ''
                                continue
                            cdash_phase = \
                                map_phases_to_cdash[current_phase]
                            if cdash_phase not in phases_encountered:
                                phases_encountered.append(cdash_phase)
                            report_data[cdash_phase]['loglines'].append(
                                text_type("{0} output for {1}:".format(
                                    cdash_phase, package['name'])))
                        elif cdash_phase:
                            before = time.clock()
                            report_data[cdash_phase]['loglines'].append(
                                xml.sax.saxutils.escape(line))
                            after = time.clock()
                            append_time += (after - before)
                tty.warn("!!! finished {0}. splitlines: {1}, find: {2}, regexp: {3}, escape: {4}, append: {5}, running total: {6}".format(package['name'], splitlines_time, find_time, regexp_time, escape_time, append_time, time.clock() - begin_time))

        phases_encountered.append('update')
        for phase in phases_encountered:
            report_data[phase]['starttime'] = self.starttime
            report_data[phase]['log'] = \
                '\n'.join(report_data[phase]['loglines'])
            errors, warnings = parse_log_events(report_data[phase]['loglines'])
            nerrors = len(errors)

            if phase == 'configure' and nerrors > 0:
                report_data[phase]['status'] = 1

            if phase == 'build':
                # Convert log output from ASCII to Unicode and escape for XML.
                def clean_log_event(event):
                    event = vars(event)
                    event['text'] = xml.sax.saxutils.escape(event['text'])
                    event['pre_context'] = xml.sax.saxutils.escape(
                        '\n'.join(event['pre_context']))
                    event['post_context'] = xml.sax.saxutils.escape(
                        '\n'.join(event['post_context']))
                    # source_file and source_line_no are either strings or
                    # the tuple (None,).  Distinguish between these two cases.
                    if event['source_file'][0] is None:
                        event['source_file'] = ''
                        event['source_line_no'] = ''
                    else:
                        event['source_file'] = xml.sax.saxutils.escape(
                            event['source_file'])
                    return event

                report_data[phase]['errors'] = []
                report_data[phase]['warnings'] = []
                for error in errors:
                    report_data[phase]['errors'].append(clean_log_event(error))
                for warning in warnings:
                    report_data[phase]['warnings'].append(
                        clean_log_event(warning))

            # Write the report.
            report_name = phase.capitalize() + ".xml"
            phase_report = os.path.join(filename, report_name)

            tty.warn("!!! writing {0} !!!".format(phase_report))
            with codecs.open(phase_report, 'w', 'utf-8') as f:
                env = spack.tengine.make_environment()
                site_template = os.path.join(self.template_dir, 'Site.xml')
                t = env.get_template(site_template)
                f.write(t.render(report_data))

                phase_template = os.path.join(self.template_dir, report_name)
                t = env.get_template(phase_template)
                f.write(t.render(report_data))
            tty.warn("!!! uploading {0} !!!".format(phase_report))
            self.upload(phase_report)

    def concretization_report(self, filename, msg):
        report_data = {}
        self.initialize_report(filename, report_data)
        report_data['starttime'] = self.starttime
        report_data['endtime'] = self.starttime
        report_data['msg'] = msg

        env = spack.tengine.make_environment()
        update_template = os.path.join(self.template_dir, 'Update.xml')
        t = env.get_template(update_template)
        output_filename = os.path.join(filename, 'Update.xml')
        with open(output_filename, 'w') as f:
            f.write(t.render(report_data))
        self.upload(output_filename)

    def initialize_report(self, filename, report_data):
        if not os.path.exists(filename):
            os.mkdir(filename)
        report_data['buildname'] = self.buildname
        report_data['buildstamp'] = self.buildstamp
        report_data['install_command'] = self.install_command
        report_data['osname'] = self.osname
        report_data['site'] = self.site

    def upload(self, filename):
        if not self.cdash_upload_url:
            return

        # Compute md5 checksum for the contents of this file.
        md5sum = checksum(hashlib.md5, filename, block_size=8192)

        buildId = None
        buildId_regexp = re.compile("<buildId>([0-9]+)</buildId>")
        opener = build_opener(HTTPHandler)
        with open(filename, 'rb') as f:
            paramsDict = {
                'build': self.buildname,
                'site': self.site,
                'stamp': self.buildstamp,
                'MD5': md5sum,
            }
            encodedParams = urlencode(paramsDict)
            url = "{0}&{1}".format(self.cdash_upload_url, encodedParams)
            request = Request(url, data=f)
            request.add_header('Content-Type', 'text/xml')
            request.add_header('Content-Length', os.path.getsize(filename))
            # By default, urllib2 only support GET and POST.
            # CDash needs expects this file to be uploaded via PUT.
            request.get_method = lambda: 'PUT'
            response = opener.open(request)
            if not buildId:
                match = buildId_regexp.search(response.read())
                if match:
                    buildId = match.group(1)
        if buildId:
            # Construct and display a helpful link if CDash responded with
            # a buildId.
            build_url = self.cdash_upload_url
            build_url = build_url[0:build_url.find("submit.php")]
            build_url += "buildSummary.php?buildid={0}".format(buildId)
            print("View your build results here:\n  {0}\n".format(build_url))
