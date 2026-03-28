import sys
from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
CONF = cfg.CONF
DOMAIN = "haminfo"

logging.register_options(CONF)
cfg.CONF(sys.argv[1:])


extra_log_level_defaults = [
        'haminfo=WARN',
        'sqlalchemy=FATAL',
        'sqlalchemy.engine.Engine=FATAL',
        'oslo.messaging=WARN',
        'oslo_messaging=WARN',
        ]
existing = logging.get_default_log_levels()
print("Default log levels {}".format(existing))


new = []
exist_dict = {}
for entry in existing:
    e_arr = entry.split('=')
    exist_dict[e_arr[0]] = e_arr[1]

for entry in extra_log_level_defaults:
    e_arr = entry.split('=')
    exist_dict[e_arr[0]] = e_arr[1]

for key in exist_dict:
    new.append("{}={}".format(key, exist_dict[key]))

print("NEW ? {}".format(new))

logging.set_defaults(default_log_levels=new)

print("List of Oslo Logging configuration options and current values")
print("=" * 80)
for c in CONF:
    print("%s = %s" % (c, CONF[c]))
print("=" * 80)

logging.setup(CONF, DOMAIN)

# Oslo Logging uses INFO as default
LOG.info("Oslo Logging")
LOG.warning("Oslo Logging")
LOG.error("Oslo Logging")

LOG.warning("DB connectionconfig option {}".format(CONF.database.connection))
