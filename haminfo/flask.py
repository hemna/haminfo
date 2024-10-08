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

from cachetools import cached, TTLCache
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
import sentry_sdk

import haminfo
from haminfo import utils, log, trace, cli_helper
from haminfo.db import db
from haminfo.conf import log as log_conf


auth = HTTPBasicAuth()
users = None
CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)
logging.register_options(CONF)

app = flask.Flask(
    utils.DOMAIN,
    static_url_path="/static",
    static_folder="web/static",
    template_folder="web/templates",
)

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
    cfg.BoolOpt('sentry_enable',
                default=False,
                help="Enable logging sentry alerts"),
    cfg.StrOpt('sentry_url',
               default='http://',
               help='The Sentry init url')
]

CONF.register_opts(web_opts, group="web")

API_KEY_HEADER = "X-Api-Key"
ttl_cache = TTLCache(maxsize=10, ttl=600)


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
    app = None

    def _get_db_session(self):
        return db.setup_session()

    def index(self):
        return flask.render_template(
            "index.html",
            version=haminfo.__version__,
            config_json=json.dumps(CONF),
        )

    @require_appkey
    def nearest(self):
        params = {}
        try:
            params = request.get_json()
        except Exception as ex:
            LOG.error("Failed to find json in request becase {}".format(ex))
            return

        LOG.debug("Lat '{}'  Lon '{}'".format(
            params.get('lat'), params.get('lon')))

        filters = None
        if 'filters' in params:
            filters = params.get('filters', None)
            if filters:
                filters = filters.split(',')

        results = []
        session = self._get_db_session()
        with session() as session:
            query = db.find_nearest_to(session, params['lat'], params['lon'],
                                       freq_band=params.get('band', None),
                                       limit=params.get('count', 1),
                                       filters=filters)

            for st, distance, az in query:
                degrees = az * 57.3
                cardinal = utils.degrees_to_cardinal(degrees)
                # LOG.debug("{} {:.2f} {:.2f} {}".format(st, distance / 1609,
                #                                        degrees, cardinal))
                dict_ = st.to_dict()
                dict_["distance"] = "{:.2f}".format(distance)
                dict_["distance_units"] = "meters"

                dict_["degrees"] = int(degrees)
                dict_["direction"] = cardinal
                results.append(dict_)

            LOG.debug(f"Returning {results}")
            db.log_request(session, params, results)

        return json.dumps(results)

    @require_appkey
    def wxnearest(self):
        """Find the N nearest weather stations from lat/lon.

           Find the stations and then return the latest weather reports
           from those stations.
        """
        params = {}
        try:
            params = request.get_json()
        except Exception as ex:
            LOG.error("Failed to find json in request becase {}".format(ex))
            return

        LOG.debug(f"wxnearest: {params}")

        results = []
        session = self._get_db_session()
        max_count = params.get('count', 1)
        with session() as session:
            query = db.find_wxnearest_to(
                session, params['lat'], params['lon'],
                limit=15
            )
            LOG.info(f"Query {query}")

            for st, distance, az in query:
                LOG.warning(f"Station {st}")
                degrees = az * 57.3
                cardinal = utils.degrees_to_cardinal(degrees)
                # LOG.debug("{} {:.2f} {:.2f} {}".format(st, distance / 1609,
                #                                        degrees, cardinal))
                dict_ = st.to_dict()
                # now find the latest report for the station
                wx_report = db.get_wx_station_report(
                    session,
                    st.id
                )

                if not wx_report:
                    LOG.error(f"Can't find a WX report for station {st.id}:{st.callsign}")
                    continue

                dict_["report"] = wx_report.to_dict()
                distance_units = "meters"
                if distance > 1000:
                    # lets put it in km instead
                    distance = distance / 1000
                    distance_units = "km"
                dict_["distance"] = "{:.2f}".format(distance)
                dict_["distance_units"] = distance_units

                dict_["degrees"] = int(degrees)
                dict_["direction"] = cardinal
                results.append(dict_)
                if len(results) >= max_count:
                    break

            LOG.debug(f"Returning {results}")
            # Need a new wx_request table for wxnow service
            db.log_wx_request(session, params, results)
        return json.dumps(results)

    def stats(self):
        stats = {}
        return json.dumps(stats)

    def requests(self):
        try:
            params = request.get_json()
        except Exception as ex:
            LOG.error("Failed to find json in request because {}".format(ex))
            return

        # last_id = params.get("last_id", 0)
        number = params.get("number", 25)
        LOG.debug(f"REQUESTS for LAST {number}")
        session = self._get_db_session()
        entries = []
        with session() as session:
            query = db.find_requests(
                session,
                number
            )

            if query:
                for r in query:
                    if r:
                        _dict = r.to_dict()
                        t = str(_dict['created'])
                        t = t[:t.rindex('.')]
                        _dict['created'] = t
                        entries.append(_dict)

        return json.dumps(entries)

    def stations(self):
        """Find stations by their callsigns."""
        params = {}
        try:
            params = request.get_json()
        except Exception as ex:
            LOG.error("Failed to find json in stations because {}".format(ex))

        callsigns = params.get('callsigns', [])
        repeater_ids = params.get('repeater_ids', [])
        LOG.debug(f"Find stations by callsign {params} or IDS {repeater_ids}")
        for call in callsigns:
            LOG.info(f"Callsign {call}")
        session = self._get_db_session()
        entries = []
        with session() as session:
            # priorities looking by ids
            if repeater_ids:
                query = db.find_stations_by_ids(
                    session,
                    repeater_ids
                )
            else:
                # Try by callsigns
                query = db.find_stations_by_callsign(
                    session,
                    callsigns
                )

            if query:
                for r in query:
                    if r:
                        _dict = r.to_dict()
                        entries.append(_dict)
            else:
                LOG.error(query)

        LOG.debug(f"Returning {len(entries)} for {callsigns}")
        return json.dumps(entries)

    @require_appkey
    @cached(cache=ttl_cache)
    def wx_stations(self):
        global ttl_cache
        LOG.debug("wx_stations:: ttl_cache={ttl_cache}")
        session = self._get_db_session()
        entries = []
        with session() as session:
            # priorities looking by ids
            query = db.find_wx_stations(session)
            if query:
                for r in query:
                    if r:
                        _dict = r.to_dict()
                        entries.append(_dict)
            else:
                LOG.error(query)

        return json.dumps(entries)

    @require_appkey
    @trace.timeit
    def wxstation_report(self):
        """Get a single weather report for a station."""
        wx_station_id = None
        try:
            LOG.info(f"REQUEST {request.args}")
            wx_station_id = request.args['wx_station_id']
        except Exception as ex:
            LOG.error("Failed to find json in wx_report because {}".format(ex))

        if not wx_station_id:
            LOG.warning("No wx_station_id in request")
            return {}

        # We need a single station id.
        session = self._get_db_session()
        with session() as session:
            report = db.get_wx_station_report(
                session,
                wx_station_id
            )
            if report:
                LOG.info(f"station report {report}")
                return json.dumps(report.to_dict())
            else:
                LOG.error(f"Can't find a report for station {wx_station_id}")
                return {}

    @require_appkey
    def wxrequests(self):
        try:
            params = request.get_json()
        except Exception as ex:
            LOG.error("Failed to find json in request because {}".format(ex))
            return

        # last_id = params.get("last_id", 0)
        number = params.get("number", 25)
        LOG.debug(f"WXREQUESTS for LAST {number}")
        session = self._get_db_session()
        entries = []
        with session() as session:
            query = db.find_wxrequests(
                session,
                number
            )

            if query:
                for r in query:
                    if r:
                        _dict = r.to_dict()
                        t = str(_dict['created'])
                        t = t[:t.rindex('.')]
                        _dict['created'] = t
                        entries.append(_dict)

        return json.dumps(entries)

    @require_appkey
    def test(self):
        LOG.warning(f"URL MAP {self.app.url_map}")


@click.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
def main(ctx):
    flask_app = create_app(ctx)
    flask_app.run(
        host=CONF.web.host_ip,
        port=CONF.web.host_port
    )


def create_app(ctx):
    python_logging.captureWarnings(True)
    version = haminfo.__version__
    if CONF.web.sentry_enable:
        sentry_sdk.init(
            dsn=CONF.web.sentry_url,
            # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for performance monitoring.
            # We recommend adjusting this value in production.
            traces_sample_rate=1.0,
            integrations=[FlaskIntegration(),
                          SqlalchemyIntegration()],
            release=f"haminfo@{version}",
        )
    session = db.setup_session()
    log_level = ctx.obj["loglevel"]
    CONF.log_opt_values(LOG, log_conf.LOG_LEVELS[log_level])
    LOG.info("haminfo_api version: {}".format(haminfo.__version__))
    LOG.info("using config file {}".format(CONF.config_file))
    LOG.info("Number of repeaters in DB {}".format(
        db.get_num_repeaters_in_db(session)))

    server = HaminfoFlask()
    server.app = app
    # app.route("/", methods=["GET"])(server.index)
    app.route("/nearest", methods=["POST"])(server.nearest)
    app.route("/stats", methods=["GET"])(server.stats)
    app.route("/requests", methods=["POST"])(server.requests)
    app.route("/stations", methods=["POST"])(server.stations)
    app.route("/wxstations", methods=["GET"])(server.wx_stations)
    app.route("/wxstation_report", methods=["GET"])(server.wxstation_report)
    app.route("/wxnearest", methods=["POST"])(server.wxnearest)
    app.route("/wxrequests", methods=["POST"])(server.wxrequests)
    app.route("/test", methods=["GET"])(server.test)
    LOG.debug("URL MAP")
    LOG.debug(f"{app.url_map}")
    return app


if __name__ == "__main__":
    main()
