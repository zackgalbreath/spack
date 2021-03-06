# Copyright 2013-2018 Lawrence Livermore National Security, LLC and other
# Spack Project Developers. See the top-level COPYRIGHT file for details.
#
# SPDX-License-Identifier: (Apache-2.0 OR MIT)

from spack import *


class PerlPerlioUtf8Strict(PerlPackage):
    """This module provides a fast and correct UTF-8 PerlIO layer."""

    homepage = "http://search.cpan.org/~leont/PerlIO-utf8_strict/lib/PerlIO/utf8_strict.pm"
    url      = "http://search.cpan.org/CPAN/authors/id/L/LE/LEONT/PerlIO-utf8_strict-0.002.tar.gz"

    version('0.002', '2e5b13efe6dfd7748e44e47f6dedb1da')
