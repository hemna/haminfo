import click
import json
import logging as python_logging
import sys

import flask
import flask_classful
from flask import request
from flask_httpauth import HTTPBasicAuth
from oslo_config import cfg
from oslo_log import log as logging
from werkzeug.security import check_password_hash, generate_password_hash

import haminfo
from haminfo import utils
from haminfo.db import db


auth = HTTPBasicAuth()
users = None
CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)
logging.register_options(CONF)

grp = cfg.OptGroup('web')
cfg.CONF.register_group(grp)
web_opts = [
    cfg.StrOpt('user',
               help='The API user for auth',
               ),
    cfg.StrOpt('password',
               help='The API users password for auth',
               ),
    cfg.StrOpt('host_ip',
               default='0.0.0.0',
               help='The hostname/ip address to listen on'
               ),
    cfg.IntOpt('host_port',
               default=80,
               help='The port to listen on for requests'
               )
]

CONF.register_opts(web_opts, group="web")

# HTTPBasicAuth doesn't work on a class method.
# This has to be out here.  Rely on the APRSDFlask
# class to initialize the users from the config
@auth.verify_password
def verify_password(username, password):
    global users

    if username in users and check_password_hash(users.get(username), password):
        return username


class HaminfoFlask(flask_classful.FlaskView):
    config = None

    def set_config(self, config):
        global users
        self.users = {}
        for user in self.config["aprsd"]["web"]["users"]:
            self.users[user] = generate_password_hash(
                self.config["aprsd"]["web"]["users"][user],
            )

        users = self.users

    def _get_db_session(self):
        engine = db.setup_connection()
        Session = db.setup_session(engine)
        return Session()

    @auth.login_required
    def index(self):
        LOG.debug("INDEX")
        return flask.render_template(
            "index.html",
            version=haminfo.__version__,
            config_json=json.dumps(CONF),
        )

    def nearest(self):
        LOG.debug("PEEPIS {}".format(request))
        LOG.debug("Lat {}".format(request.args.get('lat')))
        LOG.debug("Lon {}".format(request.args.get('lon')))
        lat = request.args.get('lat')
        lon = request.args.get('lon')
        band = request.args.get('band', None)
        count = request.args.get('count', 1)

        session = self._get_db_session()
        query = db.find_nearest_to(session, lat, lon, freq_band=band, limit=count)

        results = []

        for st, distance, az in query:
            degrees = az * 57.3
            cardinal = utils.degrees_to_cardinal(degrees)
            LOG.debug("{} {:.2f} {:.2f} {}".format(st, distance / 1609, degrees, cardinal))
            dict_ = st.to_dict()
            dict_["distance"] = "{:.2f}".format(distance / 1609)
            dict_["degrees"] = int(degrees)
            dict_["direction"] = cardinal
            results.append(dict_)

        return json.dumps(results)

    def stats(self):
        stats = {}
        return json.dumps(stats)



@click.command()
@click.option(
    "-c",
    "--config-file",
    "config_file",
    show_default=True,
    default=utils.DEFAULT_CONFIG_FILE,
    help="The aprsd config file to use for options.",
)
@click.option(
    "--loglevel",
    default="DEBUG",
    show_default=True,
    type=click.Choice(
        ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        case_sensitive=False,
    ),
    show_choices=True,
    help="The log level to use for aprsd.log",
)
def main(config_file, loglevel):
    if config_file != utils.DEFAULT_CONFIG_FILE:
        config_file = sys.argv[1:]
    else:
        config_file = ["--config-file", config_file]

    CONF(config_file, project='haminfo', version=haminfo.__version__)
    python_logging.captureWarnings(True)

    utils.setup_logging()
    CONF.log_opt_values(LOG, utils.LOG_LEVELS[loglevel])

    flask_app = flask.Flask(
        utils.DOMAIN,
        static_url_path="/static",
        static_folder="web/static",
        template_folder="web/templates",
    )

    server = HaminfoFlask()
    flask_app.route("/", methods=["GET"])(server.index)
    flask_app.route("/stats", methods=["GET"])(server.stats)
    flask_app.route("/nearest", methods=["POST"])(server.nearest)
    flask_app.run(
            host=CONF.web.host_ip,
            port=CONF.web.host_port
        )

if __name__ == "__main__":
    main()
