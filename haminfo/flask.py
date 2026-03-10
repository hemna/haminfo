"""Flask REST API for haminfo.

Provides HTTP endpoints for querying ham radio repeaters,
weather stations, and APRS data.
"""

from __future__ import annotations

import click
import json
import logging as python_logging
import time as time_mod
from datetime import datetime
from functools import wraps
from typing import Any, TYPE_CHECKING

import flask
import flask_classful
from flask import request, jsonify, Response
from flask_httpauth import HTTPBasicAuth
from oslo_config import cfg
from oslo_log import log as logging

from cachetools import cached, TTLCache
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
import sentry_sdk

import haminfo
from haminfo import utils, trace, cli_helper
from haminfo.db import db
from haminfo.conf import log as log_conf

if TYPE_CHECKING:
    from haminfo.db.models.aprs_packet import APRSPacket


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

    def __init__(self, message: str, field: str = '') -> None:
        """Initialize a validation error.

        Args:
            message: Human-readable error description.
            field: Name of the invalid field, or empty string if not
                specific to one field.
        """
        self.message = message
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
    except (ValueError, TypeError) as err:
        raise ValidationError(
            f"'lat' and 'lon' must be numeric values, got lat={lat!r}, lon={lon!r}",
            'lat/lon',
        ) from err

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
    except (ValueError, TypeError) as err:
        raise ValidationError(
            f"'count' must be an integer, got {count!r}",
            'count',
        ) from err

    if not (COUNT_MIN <= count_i <= COUNT_MAX):
        raise ValidationError(
            f"'count' must be between {COUNT_MIN} and {COUNT_MAX}, got {count_i}",
            'count',
        )

    return count_i


# Maximum callsigns per location query (matching aprs.fi limit)
MAX_CALLSIGNS = 20


def validate_callsigns(callsigns_str: Any) -> list[str]:
    """Validate and parse a comma-separated callsign string.

    Args:
        callsigns_str: Comma-separated callsign string.

    Returns:
        List of uppercased, trimmed callsign strings.

    Raises:
        ValidationError: If input is empty, not a string, or exceeds
            the maximum of 20 callsigns.
    """
    if not callsigns_str or not isinstance(callsigns_str, str):
        raise ValidationError(
            'Missing required parameter: callsign/name',
            'callsign',
        )

    raw = [cs.strip().upper() for cs in callsigns_str.split(',') if cs.strip()]

    if not raw:
        raise ValidationError(
            'At least one callsign is required',
            'callsign',
        )

    if len(raw) > MAX_CALLSIGNS:
        raise ValidationError(
            f'Maximum {MAX_CALLSIGNS} callsigns per request, got {len(raw)}',
            'callsign',
        )

    return raw


def aprs_packet_to_aprsfi_entry(packet: APRSPacket) -> dict[str, str]:
    """Convert an APRSPacket model instance to aprs.fi-compatible dict.

    All values in the returned dict are strings to match the aprs.fi API
    convention.

    Args:
        packet: APRSPacket ORM instance.

    Returns:
        Dict matching the aprs.fi location entry JSON schema.
    """
    # Map packet_type to aprs.fi type codes
    type_map = {'position': 'l', 'object': 'o', 'item': 'i'}
    aprsfi_type = type_map.get(packet.packet_type or '', 'l')

    # Convert timestamps to Unix epoch strings
    ts = packet.timestamp
    ts_epoch = str(int(ts.timestamp())) if isinstance(ts, datetime) else '0'
    recv = packet.received_at
    recv_epoch = str(int(recv.timestamp())) if isinstance(recv, datetime) else '0'

    # Build symbol string (table char + symbol char)
    sym_table = (packet.symbol_table or '') if packet.symbol_table else ''
    sym_char = (packet.symbol or '') if packet.symbol else ''
    symbol = sym_table + sym_char

    return {
        'name': (packet.from_call or '').upper(),
        'type': aprsfi_type,
        'time': ts_epoch,
        'lasttime': recv_epoch,
        'lat': str(packet.latitude) if packet.latitude is not None else '0',
        'lng': str(packet.longitude) if packet.longitude is not None else '0',
        'altitude': str(int(packet.altitude)) if packet.altitude is not None else '0',
        'course': str(packet.course) if packet.course is not None else '0',
        'speed': str(packet.speed) if packet.speed is not None else '0',
        'symbol': symbol,
        'srccall': (packet.from_call or '').upper(),
        'dstcall': (packet.to_call or '').upper(),
        'comment': packet.comment or '',
        'path': packet.path or '',
    }


def aprs_packet_to_native_entry(packet: APRSPacket) -> dict[str, Any]:
    """Convert an APRSPacket model instance to haminfo native JSON dict.

    Args:
        packet: APRSPacket ORM instance.

    Returns:
        Dict with typed values matching the haminfo native location
        response schema.

    Note:
        Timestamps are assumed to be stored in UTC. The 'Z' suffix is
        appended to indicate UTC per ISO 8601.
    """
    ts = packet.timestamp
    ts_iso = ts.isoformat() + 'Z' if isinstance(ts, datetime) else None
    recv = packet.received_at
    recv_iso = recv.isoformat() + 'Z' if isinstance(recv, datetime) else None

    sym_table = (packet.symbol_table or '') if packet.symbol_table else ''
    sym_char = (packet.symbol or '') if packet.symbol else ''

    return {
        'callsign': (packet.from_call or '').upper(),
        'latitude': float(packet.latitude) if packet.latitude is not None else None,
        'longitude': float(packet.longitude) if packet.longitude is not None else None,
        'altitude': float(packet.altitude) if packet.altitude is not None else None,
        'course': int(packet.course) if packet.course is not None else None,
        'speed': float(packet.speed) if packet.speed is not None else None,
        'symbol': sym_table + sym_char,
        'to_call': (packet.to_call or '').upper(),
        'comment': packet.comment or '',
        'path': packet.path or '',
        'timestamp': ts_iso,
        'received_at': recv_iso,
        'packet_type': packet.packet_type or 'unknown',
    }


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


def _validate_apikey_param() -> str | None:
    """Validate the ``apikey`` query parameter.

    Returns:
        Error description string if invalid, or ``None`` if valid.
    """
    if not CONF.web.api_key:
        LOG.error(
            'API key not configured in config file. Set [web] api_key in your config.'
        )
        return 'server misconfiguration'

    apikey = request.args.get('apikey')
    if not apikey:
        return 'missing parameter: apikey'

    if apikey != CONF.web.api_key:
        return 'invalid apikey'

    return None


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
            LOG.debug(f'Validation error in nearest: {ex.message}')
            return jsonify({'error': ex.message, 'field': ex.field}), 400

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
            LOG.debug(f'Validation error in wxnearest: {ex.message}')
            return jsonify({'error': ex.message, 'field': ex.field}), 400

        LOG.debug(f'wxnearest: lat={lat}, lon={lon}, count={max_count}')

        results = []
        session = self._get_db_session()
        with session() as session:
            query = db.find_wxnearest_to(
                session,
                lat,
                lon,
                limit=max_count,
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
        session = self._get_db_session()
        with session() as session:
            try:
                aprs_stats = db.get_aprs_packet_stats(session)
                stats['aprs_packets'] = aprs_stats
            except Exception as ex:
                LOG.error(f'Failed to get APRS packet stats: {ex}')
                stats['aprs_packets'] = {'error': str(ex)}
        return jsonify(stats)

    def aprsfi_location(self) -> Response:
        """Handle GET /api/get - aprs.fi-compatible location query.

        Returns location data in the exact aprs.fi JSON format so that
        APRSD plugins (aprsd-locationdata-plugin, aprsd-location-plugin)
        can use haminfo as their data source.

        All errors return HTTP 200 with ``result: "fail"`` to match
        the aprs.fi API convention.

        Returns:
            Flask JSON response with aprs.fi-compatible envelope.
        """
        start = time_mod.time()

        # Helper for aprs.fi error responses (always HTTP 200)
        def _fail(description: str) -> Response:
            return jsonify(
                {
                    'command': 'get',
                    'result': 'fail',
                    'description': description,
                }
            )

        # Validate apikey query parameter
        auth_err = _validate_apikey_param()
        if auth_err:
            return _fail(auth_err)

        # Validate 'what' parameter
        what = request.args.get('what')
        if not what:
            return _fail('missing parameter: what')
        if what != 'loc':
            return _fail(f'unsupported what value: {what}')

        # Validate 'format' parameter (optional, default json)
        fmt = request.args.get('format', 'json')
        if fmt != 'json':
            return _fail(f'unsupported format: {fmt}')

        # Validate 'name' parameter (callsigns)
        name = request.args.get('name')
        try:
            callsigns = validate_callsigns(name)
        except ValidationError as ex:
            return _fail(f'invalid name parameter: {ex.message}')

        # Query the database
        session = self._get_db_session()
        entries = []
        with session() as session:
            results = db.find_latest_positions_by_callsigns(session, callsigns)
            for pkt in results:
                entries.append(aprs_packet_to_aprsfi_entry(pkt))

        elapsed = (time_mod.time() - start) * 1000
        LOG.info(
            f'aprsfi_location: callsigns={callsigns} '
            f'found={len(entries)} elapsed={elapsed:.1f}ms'
        )

        return jsonify(
            {
                'command': 'get',
                'result': 'ok',
                'what': 'loc',
                'found': len(entries),
                'entries': entries,
            }
        )

    @require_appkey
    def location(self) -> Response | tuple[Response, int]:
        """Handle GET /api/v1/location - native haminfo location query.

        Returns location data in the haminfo native JSON format with
        typed values (floats, ints, ISO timestamps) and the standard
        data/error/meta response structure.

        Returns:
            Flask JSON response with data/error/meta envelope, or a
            tuple of (response, status_code) for error cases.
        """
        start = time_mod.time()

        # Validate 'callsign' parameter
        callsign_str = request.args.get('callsign')
        try:
            callsigns = validate_callsigns(callsign_str)
        except ValidationError as ex:
            return jsonify(
                {
                    'data': None,
                    'meta': None,
                    'error': {
                        'code': 'INVALID_PARAM',
                        'message': ex.message,
                    },
                }
            ), 400

        # Query the database
        session = self._get_db_session()
        entries = []
        with session() as session:
            results = db.find_latest_positions_by_callsigns(session, callsigns)
            for pkt in results:
                entries.append(aprs_packet_to_native_entry(pkt))

        elapsed = (time_mod.time() - start) * 1000
        LOG.info(
            f'location: callsigns={callsigns} '
            f'found={len(entries)} elapsed={elapsed:.1f}ms'
        )

        return jsonify(
            {
                'data': entries,
                'meta': {
                    'found': len(entries),
                    'requested': callsigns,
                },
                'error': None,
            }
        )

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

        # Validate that callsigns and repeater_ids are arrays, not scalars
        if callsigns and not isinstance(callsigns, list):
            return jsonify({'error': "'callsigns' must be an array of strings"}), 400
        if repeater_ids and not isinstance(repeater_ids, list):
            return jsonify(
                {'error': "'repeater_ids' must be an array of integers"}
            ), 400

        # Coerce repeater_ids to integers
        if repeater_ids:
            try:
                repeater_ids = [int(rid) for rid in repeater_ids]
            except (ValueError, TypeError):
                return jsonify(
                    {'error': "'repeater_ids' must contain valid integers"}
                ), 400

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
    app.route('/api/get', methods=['GET'])(server.aprsfi_location)
    app.route('/api/v1/location', methods=['GET'])(server.location)
    LOG.debug(f'URL MAP: {app.url_map}')
    return app


if __name__ == '__main__':
    main()
