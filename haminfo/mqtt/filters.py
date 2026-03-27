"""Packet filters for MQTT ingestion pipeline.

Filters process APRS packets received from MQTT and prepare them
for database storage.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Optional

from cachetools import cached, TTLCache
from geopy.geocoders import Nominatim
from loguru import logger

from aprsd.packets import core
from aprsd.packets.core import WeatherPacket

from haminfo.db.models.weather_report import WeatherStation, WeatherReport


@cached(cache=TTLCache(maxsize=640 * 1024, ttl=300))
def get_location(coordinates: str) -> Any:
    """Geocode coordinates to get location information.

    Results are cached for 5 minutes to avoid excessive API calls.

    Args:
        coordinates: Comma-separated lat/lon string.

    Returns:
        Nominatim location object or None.
    """
    nom = Nominatim(user_agent='haminfo')
    try:
        location = nom.geocode(
            coordinates,
            language='en',
            addressdetails=True,
        )
    except Exception as ex:
        logger.error(f'Failed to get location for {coordinates}: {ex}')
        location = None
    return location


def _convert_packet_to_dict(packet: core.Packet) -> Optional[dict]:
    """Convert an aprsd packet to a dictionary.

    Args:
        packet: An aprsd Packet object.

    Returns:
        Dictionary representation or None on failure.
    """
    try:
        if hasattr(packet, 'to_dict'):
            return packet.to_dict()
        else:
            aprs_data_json = packet.to_json()
            if isinstance(aprs_data_json, str):
                return json.loads(aprs_data_json)
            return aprs_data_json
    except Exception as ex:
        logger.error(f'Failed to convert aprsd packet to dict: {ex}')
        return None


class APRSPacketFilter:
    """Filter that validates packets are proper APRS packet objects."""

    def filter(self, packet: Any) -> Optional[core.Packet]:
        """Validate that the packet is an APRS packet.

        Args:
            packet: Packet to validate.

        Returns:
            The packet if valid, None otherwise.
        """
        if not isinstance(packet, core.Packet):
            return None
        return packet


class WeatherPacketFilter:
    """Filter that processes weather packets and saves them to the database.

    Handles finding or creating weather stations and creating weather
    reports from incoming weather packets.
    """

    def __init__(
        self,
        session_factory: Any,
        stats: dict,
        stats_lock: threading.Lock,
        reports: list,
    ):
        """Initialize the weather packet filter.

        Args:
            session_factory: SQLAlchemy session factory for creating sessions.
            stats: Shared statistics dictionary.
            stats_lock: Lock for thread-safe stats access.
            reports: List to accumulate weather reports for bulk saving.
        """
        self.session_factory = session_factory
        self.stats = stats
        self.stats_lock = stats_lock
        self.reports = reports

    def filter(self, packet: Any) -> Optional[WeatherPacket]:
        """Process weather packet: find/create station, create report.

        Args:
            packet: Packet to process.

        Returns:
            The packet if successfully processed, None otherwise.
        """
        if not isinstance(packet, WeatherPacket):
            return packet

        aprs_data = _convert_packet_to_dict(packet)
        if aprs_data is None:
            return None

        station = self._find_or_create_station(aprs_data)
        if station is None:
            return None

        return self._create_report(aprs_data, station)

    def _find_or_create_station(self, aprs_data: dict) -> Optional[WeatherStation]:
        """Find an existing station or create a new one.

        Args:
            aprs_data: Packet data dictionary.

        Returns:
            WeatherStation or None on failure.
        """
        from_call = aprs_data.get('from_call', 'unknown')
        session = self.session_factory()

        try:
            station = WeatherStation.find_station_by_callsign(session, from_call)
            if station:
                return station

            logger.info(f'Creating new station for {from_call}')
            station = WeatherStation.from_json(aprs_data)
            if not station:
                logger.warning(
                    f'Failed to create station from packet data for {from_call}'
                )
                return None

            # Geocode to get country code
            coordinates = f'{station.latitude:0.6f}, {station.longitude:0.6f}'
            location = get_location(coordinates)
            if location and hasattr(location, 'raw'):
                address = location.raw.get('address')
                if address:
                    station.country_code = address.get('country_code', '')
                else:
                    logger.warning(f'No address found for coordinates {coordinates}')

            session.add(station)
            session.commit()
            return station
        except Exception as ex:
            session.rollback()
            logger.error(f'Failed to find/create station {from_call}: {ex}')
            return None
        finally:
            session.close()

    def _create_report(
        self, aprs_data: dict, station: WeatherStation
    ) -> Optional[bool]:
        """Create a weather report from packet data.

        Args:
            aprs_data: Packet data dictionary.
            station: The weather station this report belongs to.

        Returns:
            True if report was created successfully, None otherwise.
        """
        try:
            report = WeatherReport.from_json(aprs_data, station.id)
        except Exception as ex:
            logger.error(f'Failed to create WeatherReport: {ex}')
            logger.debug(f'Packet data: {aprs_data}')
            return None

        try:
            if report.is_valid():
                self.reports.append(report)
                with self.stats_lock:
                    self.stats['report_counter'] = (
                        self.stats.get('report_counter', 0) + 1
                    )
                return True  # Signal success
            else:
                return None
        except ValueError as ex:
            logger.error(f'Invalid weather report: {ex}')
            return None
        except Exception as ex:
            logger.error(f'Failed to process weather report: {ex}')
            return None


class IngestPacketFilter:
    """Passthrough filter for the ingestion pipeline."""

    def filter(self, packet: Any) -> Any:
        """Pass the packet through unchanged."""
        return packet
