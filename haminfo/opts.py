import itertools

from haminfo import flask
from haminfo.db import db


def list_opts():
    return [
        ('database',
         itertools.chain(
             db.database_opts
         )),
        ('web',
         itertools.chain(
             flask.web_opts

         ))
    ]


def set_external_library_defaults():
    """Set default config options for external libs."""
    pass
