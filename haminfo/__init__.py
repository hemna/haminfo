"""Top-level package for haminfo."""

from importlib.metadata import PackageNotFoundError, version

__author__ = """haminfo"""
__email__ = 'waboring@hemna.com'

try:
    __version__ = version("haminfo")
except PackageNotFoundError:
    pass
