from pathlib import Path

from oslo_config import cfg


haminfo_opts = [
    cfg.BoolOpt(
        "trace_enabled",
        default=False,
        help="Enable code tracing",
    ),
]



def register_opts(config):
    config.register_opts(haminfo_opts)


def list_opts():
    return {
        "DEFAULT": haminfo_opts
    }
