# Copyright 2013-2018 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from spack import *


class Opium(Package):
    """DFT pseudopotential generation project"""

    homepage = "https://opium.sourceforge.net/index.html"
    url = "https://downloads.sourceforge.net/project/opium/opium/opium-v3.8/opium-v3.8-src.tgz"

    version('3.8', 'f710c0f869e70352b4a510c31e13bf9f')

    depends_on('blas')
    depends_on('lapack')

    def install(self, spec, prefix):
        libs = spec['lapack'].libs + spec['blas'].libs
        options = ['LDFLAGS=%s' % libs.ld_flags]

        configure(*options)
        with working_dir("src", create=False):
            make("all-subdirs")
            make("opium")

        # opium not have a make install :-((
        mkdirp(self.prefix.bin)
        install(join_path(self.stage.source_path, 'opium'),
                self.prefix.bin)
