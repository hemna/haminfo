"""Flask REST API for haminfo.

Provides HTTP endpoints for querying ham radio repeaters,
weather stations, and APRS data.
"""

from __future__ import annotations

import click
import json
import logging as python_logging
import sys
from functools import wraps
from typing import Any

import flask
import flask_classful
from flask import abort, request, jsonify, Response
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
    static_url_path='/static',
    static_folder='web/static',
    template_folder='web/templates',
)

grp = cfg.OptGroup('web')
cfg.CONF.register_group(grp)
web_opts = [
    cfg.StrOpt(
        'host_ip', default='0.0.0.0', help='The hostname/ip address to listen on'
    ),
    cfg.IntOpt('host_port', default=80, help='The port to listen on for requests'),
    cfg.StrOpt(
        'api_key',
        help='The api key to allow requests incoming. Must be set in config file.',
        secret=True,
    ),
    cfg.BoolOpt('sentry_enable', default=False, help='Enable logging sentry alerts'),
    cfg.StrOpt(
        'sentry_url',
        default='',
        help='The Sentry init url',
        secret=True,
    ),
]

CONF.register_opts(web_opts, group='web')

API_KEY_HEADER = 'X-Api-Key'
ttl_cache = TTLCache(maxsize=10, ttl=600)

# Validation constants
LAT_MIN, LAT_MAX = -90.0, 90.0
LON_MIN, LON_MAX = -180.0, 180.0
COUNT_MIN, COUNT_MAX = 1, 100
DEFAULT_COUNT = 10


class ValidationError(Exception):
    """Raised when request input validation fails."""

    def __init__(self, message: str, field: str = ''):
        self.field = field
        super().__init__(message)


def validate_lat_lon(lat: Any, lon: Any) -> tuple[float, float]:
    """Validate and convert latitude/longitude values.

    Args:
        lat: Latitude value (string or numeric).
        lon: Longitude value (string or numeric).

    Returns:
        Tuple of (latitude, longitude) as floats.

    Raises:
        ValidationError: If values are missing or out of range.
    """
    if lat is None or lon is None:
        raise ValidationError("Both 'lat' and 'lon' are required", 'lat/lon')

    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (ValueError, TypeError):
        raise ValidationError(
            f"'lat' and 'lon' must be numeric values, got lat={lat!r}, lon={lon!r}",
            'lat/lon',
        )

    if not (LAT_MIN <= lat_f <= LAT_MAX):
        raise ValidationError(
            f"'lat' must be between {LAT_MIN} and {LAT_MAX}, got {lat_f}",
            'lat',
        )
    if not (LON_MIN <= lon_f <= LON_MAX):
        raise ValidationError(
            f"'lon' must be between {LON_MIN} and {LON_MAX}, got {lon_f}",
            'lon',
        )

    return lat_f, lon_f


def validate_count(count: Any, default: int = DEFAULT_COUNT) -> int:
    """Validate and convert a count parameter.

    Args:
        count: Count value to validate.
        default: Default count if None.

    Returns:
        Validated count as integer.

    Raises:
        ValidationError: If count is not a valid integer in range.
    """
    if count is None:
        return default

    try:
        count_i = int(count)
    except (ValueError, TypeError):
        raise ValidationError(
            f"'count' must be an integer, got {count!r}",
            'count',
        )

    if not (COUNT_MIN <= count_i <= COUNT_MAX):
        raise ValidationError(
            f"'count' must be between {COUNT_MIN} and {COUNT_MAX}, got {count_i}",
            'count',
        )

    return count_i


def require_appkey(view_function):
    """Decorator to require a valid API key in request headers.

    The API key must be configured in the config file under [web] api_key.
    """

    @wraps(view_function)
    def decorated_function(*args, **kwargs):
        # Check that API key is configured
        if not CONF.web.api_key:
            LOG.error(
                'API key not configured in config file. '
                'Set [web] api_key in your config.'
            )
            return jsonify({'error': 'Server misconfiguration: API key not set'}), 500

        headers = request.headers
        apikey = headers.get(API_KEY_HEADER, None)
        if not apikey:
            return jsonify({'error': 'Unauthorized: API key required'}), 401

        if apikey == CONF.web.api_key:
            return view_function(*args, **kwargs)
        else:
            return jsonify({'error': 'Unauthorized: Invalid API key'}), 401

    return decorated_function


class HaminfoFlask(flask_classful.FlaskView):
    app: flask.Flask = None  # type: ignore[assignment]

    def _get_db_session(self):
        return db.setup_session()

    def index(self):
        return flask.render_template(
            'index.html',
            version=haminfo.__version__,
            config_json=json.dumps(CONF),
        )

    @require_appkey
    def nearest(self):
        """Find nearest repeaters to a given lat/lon."""
        params = {}
        try:
            params = request.get_json()
        except Exception as ex:
            LOG.error(f'Failed to parse JSON request body: {ex}')
            return jsonify({'error': 'Invalid JSON request body'}), 400

        if not params:
            return jsonify({'error': 'Request body is required'}), 400

        # Validate inputs
        try:
            lat, lon = validate_lat_lon(params.get('lat'), params.get('lon'))
            count = validate_count(params.get('count'), default=1)
        except ValidationError as ex:
            return jsonify({'error': str(ex), 'field': ex.field}), 400

        LOG.debug(f"Lat '{lat}'  Lon '{lon}'")

        filters = None
        if 'filters' in params:
            filters = params.get('filters', None)
            if filters:
                filters = filters.split(',')

        results = []
        session = self._get_db_session()
        with session() as session:
            query = db.find_nearest_to(
                session,
                lat,
                lon,
                freq_band=params.get('band', None),
                limit=count,
                filters=filters,
            )

            for st, distance, az in query:
                degrees = az * 57.3
                cardinal = utils.degrees_to_cardinal(degrees)
                dict_ = st.to_dict()
                dict_['distance'] = f'{distance:.2f}'
                dict_['distance_units'] = 'meters'
                dict_['degrees'] = int(degrees)
                dict_['direction'] = cardinal
                results.append(dict_)

            LOG.debug(f'Returning {len(results)} results')
            db.log_request(session, params, results)

        return jsonify(results)

    @require_appkey
    def wxnearest(self):
        """Find the N nearest weather stations from lat/lon.

        Finds the stations and returns the latest weather reports
        from those stations.
        """
        params = {}
        try:
            params = request.get_json()
        except Exception as ex:
            LOG.error(f'Failed to parse JSON request body: {ex}')
            return jsonify({'error': 'Invalid JSON request body'}), 400

        if not params:
            return jsonify({'error': 'Request body is required'}), 400

        # Validate inputs
        try:
            lat, lon = validate_lat_lon(params.get('lat'), params.get('lon'))
            max_count = validate_count(params.get('count'), default=1)
        except ValidationError as ex:
            return jsonify({'error': str(ex), 'field': ex.field}), 400

        LOG.debug(f'wxnearest: lat={lat}, lon={lon}, count={max_count}')

        results = []
        session = self._get_db_session()
        with session() as session:
            query = db.find_wxnearest_to(
                session,
                lat,
                lon,
                limit=15,
            )
            LOG.info(f'Query {query}')

            for st, distance, az in query:
                LOG.debug(f'Station {st}')
                degrees = az * 57.3
                cardinal = utils.degrees_to_cardinal(degrees)
                dict_ = st.to_dict()

                # Find the latest report for the station
                wx_report = db.get_wx_station_report(session, st.id)
                if not wx_report:
                    LOG.warning(
                        f'No weather report found for station {st.id}:{st.callsign}'
                    )
                    continue

                dict_['report'] = wx_report.to_dict()
                distance_units = 'meters'
                if distance > 1000:
                    distance = distance / 1000
                    distance_units = 'km'
                dict_['distance'] = f'{distance:.2f}'
                dict_['distance_units'] = distance_units
                dict_['degrees'] = int(degrees)
                dict_['direction'] = cardinal
                results.append(dict_)
                if len(results) >= max_count:
                    break

            LOG.debug(f'Returning {len(results)} results')
            db.log_wx_request(session, params, results)

        return jsonify(results)

    def stats(self):
        """Return application statistics."""
        stats = {}
        return jsonify(stats)

    def requests(self):
        """Return recent API request history."""
        try:
            params = request.get_json()
        except Exception as ex:
            LOG.error(f'Failed to parse JSON request body: {ex}')
            return jsonify({'error': 'Invalid JSON request body'}), 400

        if not params:
            params = {}

        number = params.get('number', 25)
        try:
            number = int(number)
            number = min(max(number, 1), 500)
        except (ValueError, TypeError):
            return jsonify({'error': "'number' must be an integer"}), 400

        LOG.debug(f'REQUESTS for LAST {number}')
        session = self._get_db_session()
        entries = []
        with session() as session:
            query = db.find_requests(session, number)
            if query:
                for r in query:
                    if r:
                        _dict = r.to_dict()
                        t = str(_dict['created'])
                        t = t[: t.rindex('.')]
                        _dict['created'] = t
                        entries.append(_dict)

        return jsonify(entries)

    def stations(self):
        """Find stations by their callsigns or IDs."""
        params = {}
        try:
            params = request.get_json()
        except Exception as ex:
            LOG.error(f'Failed to parse JSON request body: {ex}')
            return jsonify({'error': 'Invalid JSON request body'}), 400

        if not params:
            return jsonify({'error': 'Request body is required'}), 400

        callsigns = params.get('callsigns', [])
        repeater_ids = params.get('repeater_ids', [])

        if not callsigns and not repeater_ids:
            return jsonify(
                {'error': "Either 'callsigns' or 'repeater_ids' is required"}
            ), 400

        LOG.debug(f'Find stations: callsigns={callsigns}, ids={repeater_ids}')
        session = self._get_db_session()
        entries = []
        with session() as session:
            if repeater_ids:
                query = db.find_stations_by_ids(session, repeater_ids)
            else:
                query = db.find_stations_by_callsign(session, callsigns)

            if query:
                for r in query:
                    if r:
                        _dict = r.to_dict()
                        entries.append(_dict)

        LOG.debug(f'Returning {len(entries)} stations')
        return jsonify(entries)

    @require_appkey
    @cached(cache=ttl_cache)
    def wx_stations(self):
        """Get all weather stations."""
        LOG.debug(f'wx_stations:: cache info={ttl_cache.currsize}/{ttl_cache.maxsize}')
        session = self._get_db_session()
        entries = []
        with session() as session:
            query = db.find_wx_stations(session)
            if query:
                for r in query:
                    if r:
                        _dict = r.to_dict()
                        entries.append(_dict)

        return jsonify(entries)

    @require_appkey
    @trace.timeit
    def wxstation_report(self):
        """Get a single weather report for a station."""
        wx_station_id = request.args.get('wx_station_id')
        if not wx_station_id:
            return jsonify({'error': "'wx_station_id' parameter is required"}), 400

        # Validate station ID
        try:
            wx_station_id = int(wx_station_id)
        except (ValueError, TypeError):
            return jsonify({'error': "'wx_station_id' must be an integer"}), 400

        session = self._get_db_session()
        with session() as session:
            report = db.get_wx_station_report(session, wx_station_id)
            if report:
                LOG.info(f'Found report for station {wx_station_id}')
                return jsonify(report.to_dict())
            else:
                return jsonify(
                    {'error': f'No report found for station {wx_station_id}'}
                ), 404

    @require_appkey
    def wxrequests(self):
        """Return recent weather request history."""
        try:
            params = request.get_json()
        except Exception as ex:
            LOG.error(f'Failed to parse JSON request body: {ex}')
            return jsonify({'error': 'Invalid JSON request body'}), 400

        if not params:
            params = {}

        number = params.get('number', 25)
        try:
            number = int(number)
            number = min(max(number, 1), 500)
        except (ValueError, TypeError):
            return jsonify({'error': "'number' must be an integer"}), 400

        LOG.debug(f'WXREQUESTS for LAST {number}')
        session = self._get_db_session()
        entries = []
        with session() as session:
            query = db.find_wxrequests(session, number)
            if query:
                for r in query:
                    if r:
                        _dict = r.to_dict()
                        t = str(_dict['created'])
                        t = t[: t.rindex('.')]
                        _dict['created'] = t
                        entries.append(_dict)

        return jsonify(entries)

    @require_appkey
    def test(self):
        """Test endpoint to verify API is working."""
        LOG.debug(f'URL MAP: {self.app.url_map}')
        return jsonify({'status': 'ok', 'version': haminfo.__version__})


@click.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
def main(ctx):
    flask_app = create_app(ctx)
    flask_app.run(host=CONF.web.host_ip, port=CONF.web.host_port)


def create_app(ctx):
    python_logging.captureWarnings(True)
    version = haminfo.__version__

    # Validate API key is configured
    if not CONF.web.api_key:
        LOG.warning(
            'No API key configured! Set [web] api_key in your config file. '
            'API endpoints requiring authentication will return 500 errors.'
        )

    if CONF.web.sentry_enable:
        if not CONF.web.sentry_url:
            LOG.warning('Sentry enabled but sentry_url is not configured')
        else:
            sentry_sdk.init(
                dsn=CONF.web.sentry_url,
                traces_sample_rate=1.0,
                integrations=[FlaskIntegration(), SqlalchemyIntegration()],
                release=f'haminfo@{version}',
            )

    session = db.setup_session()
    log_level = ctx.obj['loglevel']
    CONF.log_opt_values(LOG, log_conf.LOG_LEVELS[log_level])
    LOG.info(f'haminfo_api version: {haminfo.__version__}')
    LOG.info(f'using config file {CONF.config_file}')
    LOG.info(f'Number of repeaters in DB: {db.get_num_repeaters_in_db(session)}')

    server = HaminfoFlask()
    server.app = app
    app.route('/nearest', methods=['POST'])(server.nearest)
    app.route('/stats', methods=['GET'])(server.stats)
    app.route('/requests', methods=['POST'])(server.requests)
    app.route('/stations', methods=['POST'])(server.stations)
    app.route('/wxstations', methods=['GET'])(server.wx_stations)
    app.route('/wxstation_report', methods=['GET'])(server.wxstation_report)
    app.route('/wxnearest', methods=['POST'])(server.wxnearest)
    app.route('/wxrequests', methods=['POST'])(server.wxrequests)
    app.route('/test', methods=['GET'])(server.test)
    LOG.debug(f'URL MAP: {app.url_map}')
    return app


if __name__ == '__main__':
    main()
