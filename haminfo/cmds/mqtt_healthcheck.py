import click
import datetime
import json
import os
import sys

from oslo_config import cfg
from oslo_log import log as logging

import haminfo
from haminfo.main import cli
from haminfo import cli_helper
from haminfo import utils


CONF = cfg.CONF
LOG = logging.getLogger(utils.DOMAIN)

# Maximum age of keepalive file before considering unhealthy
MAX_FILE_AGE_MINUTES = 5
# Maximum consecutive zero-packet intervals before unhealthy
MAX_ZERO_INTERVALS = 2


@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.pass_context
@cli_helper.process_standard_options
def mqtt_healthcheck(ctx):
    """MQTT healthcheck - verifies MQTT ingestion is working properly."""
    LOG.info(f'Haminfo MQTT Healthcheck version: {haminfo.__version__}')

    now = datetime.datetime.now()
    exit_code = 0
    errors = []

    # Check 1: Keepalive file exists and is recent
    try:
        modify_time = os.path.getmtime(CONF.mqtt.keepalive_file)
        modify_date = datetime.datetime.fromtimestamp(modify_time)
        max_delta = datetime.timedelta(minutes=MAX_FILE_AGE_MINUTES)
        diff = now - modify_date
        if diff > max_delta:
            errors.append(f'Keepalive file is stale: {diff} old (max: {max_delta})')
            exit_code = 1
        else:
            LOG.info(f'Keepalive file age: {diff}')
    except FileNotFoundError:
        errors.append(f'Keepalive file not found: {CONF.mqtt.keepalive_file}')
        exit_code = 1
    except Exception as ex:
        errors.append(f'Error checking keepalive file: {ex}')
        exit_code = 1

    # Check 2: Parse and verify keepalive contents
    keepalive_data = None
    try:
        with open(CONF.mqtt.keepalive_file) as fp:
            keepalive_data = json.load(fp)
        LOG.debug(f'Keepalive data: {keepalive_data}')
    except FileNotFoundError:
        pass  # Already handled above
    except json.JSONDecodeError as ex:
        errors.append(f'Invalid JSON in keepalive file: {ex}')
        exit_code = 1
    except Exception as ex:
        errors.append(f'Error reading keepalive file: {ex}')
        exit_code = 1

    if keepalive_data:
        # Check 3: Verify all threads are running
        if 'threads' in keepalive_data:
            for thread_name, is_alive in keepalive_data['threads'].items():
                if not is_alive:
                    errors.append(f'Thread {thread_name} is not running')
                    exit_code = 1
                else:
                    LOG.info(f'Thread {thread_name}: OK')

        # Check 4: Verify MQTT connection state
        mqtt_state = keepalive_data.get('mqtt', {})
        if not mqtt_state.get('connected', False):
            errors.append('MQTT client is not connected')
            exit_code = 1
        elif not mqtt_state.get('subscribed', False):
            errors.append('MQTT client is not subscribed')
            exit_code = 1
        else:
            LOG.info('MQTT connection: OK')

        # Check message age if available
        last_msg_age = mqtt_state.get('last_message_age', -1)
        if last_msg_age > 120:  # 2 minutes
            errors.append(f'No MQTT messages for {last_msg_age:.0f}s')
            exit_code = 1
        elif last_msg_age >= 0:
            LOG.info(f'Last MQTT message: {last_msg_age:.0f}s ago')

        # Check 5: Verify packet flow
        packets = keepalive_data.get('packets', {})
        zero_intervals = packets.get('zero_intervals', 0)
        if zero_intervals >= MAX_ZERO_INTERVALS:
            errors.append(f'No packets for {zero_intervals} consecutive intervals')
            exit_code = 1
        else:
            last_received = packets.get('last_interval_received', 0)
            total_received = packets.get('total_received', 0)
            LOG.info(f'Packets: {last_received} last interval, {total_received} total')

    # Report results
    if errors:
        for error in errors:
            LOG.error(f'UNHEALTHY: {error}')
        sys.exit(exit_code)
    else:
        LOG.info('Healthcheck PASSED')
        return 0
