"""Top-level package for haminfo."""

import pbr.version

__author__ = """haminfo"""
__email__ = 'waboring@hemna.com'

__version__ = pbr.version.VersionInfo("haminfo").version_string()
if not __version__:
    __version__ = '0.1.0'
