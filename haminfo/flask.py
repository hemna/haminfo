import click
import json
import logging as python_logging
import sys
from functools import wraps
import flask
import flask_classful
from flask import abort, request, jsonify
from flask_httpauth import HTTPBasicAuth
from oslo_config import cfg
from oslo_log import log as logging

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
    cfg.StrOpt('host_ip',
               default='0.0.0.0',
               help='The hostname/ip address to listen on'
               ),
    cfg.IntOpt('host_port',
               default=80,
               help='The port to listen on for requests'
               ),
    cfg.StrOpt('api_key',
               default='abcdefg',
               help='The api key to allow requests incoming.'
               ),
]

CONF.register_opts(web_opts, group="web")

API_KEY_HEADER = "X-Api-Key"

# TODO(waboring) add real users and user management
# and api key token creation
# For now, we hard code a token in the config file
# that needs to be sent along in the request header
# as X-Api-Key: <token>


# The actual decorator function
def require_appkey(view_function):
    @wraps(view_function)
    # the new, post-decoration function. Note *args and **kwargs here.
    def decorated_function(*args, **kwargs):
        headers = request.headers
        apikey = headers.get(API_KEY_HEADER, None)
        if not apikey:
            return jsonify({"message": "ERROR: Unauthorized"}), 401

        if apikey == CONF.web.api_key:
            return view_function(*args, **kwargs)
        else:
            abort(401)
    return decorated_function


class HaminfoFlask(flask_classful.FlaskView):

    def _get_db_session(self):
        engine = db.setup_connection()
        session = db.setup_session(engine)
        return session()

    def index(self):
        LOG.debug("INDEX")
        return flask.render_template(
            "index.html",
            version=haminfo.__version__,
            config_json=json.dumps(CONF),
        )

    @require_appkey
    def nearest(self):
        LOG.debug("Lat {}".format(request.args.get('lat')))
        LOG.debug("Lon {}".format(request.args.get('lon')))
        try:
            params = request.get_json()
        except Exception as ex:
            LOG.error("Failed to find json in request becase {}".format(ex))
            return

        filters = params.get('filters', None)
        if filters:
            filters = filters.split(',')

        session = self._get_db_session()
        query = db.find_nearest_to(session, params['lat'], params['lon'],
                                   freq_band=params.get('band', None),
                                   limit=params.get('count', 1),
                                   filters=filters)

        results = []

        for st, distance, az in query:
            degrees = az * 57.3
            cardinal = utils.degrees_to_cardinal(degrees)
            #LOG.debug("{} {:.2f} {:.2f} {}".format(st, distance / 1609,
            #                                       degrees, cardinal))
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
    "--log-level",
    "log_level",
    default="DEBUG",
    show_default=True,
    type=click.Choice(
        ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        case_sensitive=False,
    ),
    show_choices=True,
    help="The log level to use for aprsd.log",
)
def main(config_file, log_level):
    conf_file = config_file
    if config_file != utils.DEFAULT_CONFIG_FILE:
        config_file = sys.argv[1:]
    else:
        config_file = ["--config-file", config_file]

    CONF(config_file, project='haminfo', version=haminfo.__version__)
    python_logging.captureWarnings(True)
    utils.setup_logging()

    LOG.info("haminfo_api version: {}".format(haminfo.__version__))
    LOG.info("using config file {}".format(conf_file))

    CONF.log_opt_values(LOG, utils.LOG_LEVELS[log_level])

    flask_app = flask.Flask(
        utils.DOMAIN,
        static_url_path="/static",
        static_folder="web/static",
        template_folder="web/templates",
    )

    server = HaminfoFlask()
    flask_app.route("/", methods=["GET"])(server.index)
    flask_app.route("/nearest", methods=["POST"])(server.nearest)
    flask_app.run(
            host=CONF.web.host_ip,
            port=CONF.web.host_port
        )


if __name__ == "__main__":
    main()
