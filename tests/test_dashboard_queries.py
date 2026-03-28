# tests/test_dashboard_queries.py
"""Tests for dashboard query helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from haminfo.db.models.aprs_packet import APRSPacket
from haminfo.db.models.weather_report import WeatherStation, WeatherReport
from haminfo.dashboard.queries import (
    get_dashboard_stats,
    get_top_stations,
    get_country_breakdown,
    get_hourly_distribution,
    get_recent_packets,
)


class TestGetDashboardStats:
    """Tests for get_dashboard_stats function."""

    def test_returns_dict_with_required_keys(self, db_session):
        """Returns dict with total_packets_24h, unique_stations, countries, weather_stations."""
        result = get_dashboard_stats(db_session)

        assert isinstance(result, dict)
        assert 'total_packets_24h' in result
        assert 'unique_stations' in result
        assert 'countries' in result
        assert 'weather_stations' in result

    def test_counts_packets_in_last_24h(self, db_session):
        """Counts only packets from the last 24 hours."""
        now = datetime.utcnow()

        # Add packet from 12 hours ago (should be counted)
        recent_packet = APRSPacket(
            from_call='N0CALL',
            to_call='APRS',
            timestamp=now - timedelta(hours=12),
            received_at=now - timedelta(hours=12),
            raw='N0CALL>APRS:test',
            packet_type='position',
            latitude=40.0,
            longitude=-105.0,
        )
        db_session.add(recent_packet)

        # Add packet from 48 hours ago (should NOT be counted)
        old_packet = APRSPacket(
            from_call='W0ABC',
            to_call='APRS',
            timestamp=now - timedelta(hours=48),
            received_at=now - timedelta(hours=48),
            raw='W0ABC>APRS:test',
            packet_type='position',
            latitude=41.0,
            longitude=-106.0,
        )
        db_session.add(old_packet)
        db_session.commit()

        result = get_dashboard_stats(db_session)

        assert result['total_packets_24h'] == 1
        assert result['unique_stations'] == 1

    def test_counts_unique_stations(self, db_session):
        """Counts unique callsigns in the last 24 hours."""
        now = datetime.utcnow()

        # Add multiple packets from same station
        for i in range(3):
            packet = APRSPacket(
                from_call='N0CALL',
                to_call='APRS',
                timestamp=now - timedelta(hours=i + 1),
                received_at=now - timedelta(hours=i + 1),
                raw=f'N0CALL>APRS:test{i}',
                packet_type='position',
            )
            db_session.add(packet)

        # Add packet from different station
        packet2 = APRSPacket(
            from_call='W0ABC',
            to_call='APRS',
            timestamp=now - timedelta(hours=1),
            received_at=now - timedelta(hours=1),
            raw='W0ABC>APRS:test',
            packet_type='position',
        )
        db_session.add(packet2)
        db_session.commit()

        result = get_dashboard_stats(db_session)

        assert result['total_packets_24h'] == 4
        assert result['unique_stations'] == 2

    def test_counts_weather_stations(self, db_session):
        """Counts total weather stations."""
        # Add weather stations
        for i in range(3):
            station = WeatherStation(
                id=i + 1,
                callsign=f'WX{i}TEST',
                latitude=40.0 + i,
                longitude=-105.0,
            )
            db_session.add(station)
        db_session.commit()

        result = get_dashboard_stats(db_session)

        assert result['weather_stations'] == 3


class TestGetTopStations:
    """Tests for get_top_stations function."""

    def test_returns_list(self, db_session):
        """Returns a list."""
        result = get_top_stations(db_session)
        assert isinstance(result, list)

    def test_respects_limit(self, db_session):
        """Respects the limit parameter."""
        now = datetime.utcnow()

        # Add packets from 10 different stations
        for i in range(10):
            packet = APRSPacket(
                from_call=f'N{i}CALL',
                to_call='APRS',
                timestamp=now - timedelta(hours=1),
                received_at=now - timedelta(hours=1),
                raw=f'N{i}CALL>APRS:test',
                packet_type='position',
            )
            db_session.add(packet)
        db_session.commit()

        result = get_top_stations(db_session, limit=5)

        assert len(result) <= 5

    def test_orders_by_packet_count(self, db_session):
        """Orders stations by packet count descending."""
        now = datetime.utcnow()

        # Station with 5 packets
        for i in range(5):
            packet = APRSPacket(
                from_call='N0CALL',
                to_call='APRS',
                timestamp=now - timedelta(hours=i + 1),
                received_at=now - timedelta(hours=i + 1),
                raw=f'N0CALL>APRS:test{i}',
                packet_type='position',
            )
            db_session.add(packet)

        # Station with 2 packets
        for i in range(2):
            packet = APRSPacket(
                from_call='W0ABC',
                to_call='APRS',
                timestamp=now - timedelta(hours=i + 1),
                received_at=now - timedelta(hours=i + 1),
                raw=f'W0ABC>APRS:test{i}',
                packet_type='position',
            )
            db_session.add(packet)
        db_session.commit()

        result = get_top_stations(db_session, limit=10)

        assert len(result) >= 2
        assert result[0]['callsign'] == 'N0CALL'
        assert result[0]['count'] == 5
        assert result[1]['callsign'] == 'W0ABC'
        assert result[1]['count'] == 2


class TestGetCountryBreakdown:
    """Tests for get_country_breakdown function."""

    def test_returns_list(self, db_session):
        """Returns a list."""
        result = get_country_breakdown(db_session)
        assert isinstance(result, list)

    def test_returns_country_info(self, db_session):
        """Returns country_code, country_name, count for each entry."""
        now = datetime.utcnow()

        # Add US station
        packet = APRSPacket(
            from_call='N0CALL',
            to_call='APRS',
            timestamp=now - timedelta(hours=1),
            received_at=now - timedelta(hours=1),
            raw='N0CALL>APRS:test',
            packet_type='position',
        )
        db_session.add(packet)
        db_session.commit()

        result = get_country_breakdown(db_session)

        if len(result) > 0:
            entry = result[0]
            assert 'country_code' in entry
            assert 'country_name' in entry
            assert 'count' in entry


class TestGetHourlyDistribution:
    """Tests for get_hourly_distribution function."""

    def test_returns_labels_and_values(self, db_session):
        """Returns dict with labels and values arrays."""
        result = get_hourly_distribution(db_session)

        assert isinstance(result, dict)
        assert 'labels' in result
        assert 'values' in result
        assert isinstance(result['labels'], list)
        assert isinstance(result['values'], list)

    def test_returns_24_items(self, db_session):
        """Returns exactly 24 items for each hour."""
        result = get_hourly_distribution(db_session)

        assert len(result['labels']) == 24
        assert len(result['values']) == 24


class TestGetRecentPackets:
    """Tests for get_recent_packets function."""

    def test_returns_list(self, db_session):
        """Returns a list."""
        result = get_recent_packets(db_session)
        assert isinstance(result, list)

    def test_respects_limit(self, db_session):
        """Respects the limit parameter."""
        now = datetime.utcnow()

        # Add 20 packets
        for i in range(20):
            packet = APRSPacket(
                from_call=f'N{i}CALL',
                to_call='APRS',
                timestamp=now - timedelta(minutes=i),
                received_at=now - timedelta(minutes=i),
                raw=f'N{i}CALL>APRS:test',
                packet_type='position',
            )
            db_session.add(packet)
        db_session.commit()

        result = get_recent_packets(db_session, limit=10)

        assert len(result) <= 10

    def test_orders_by_received_at_desc(self, db_session):
        """Orders packets by received_at descending (most recent first)."""
        now = datetime.utcnow()

        # Add packets with different timestamps
        old_packet = APRSPacket(
            from_call='N0OLD',
            to_call='APRS',
            timestamp=now - timedelta(hours=2),
            received_at=now - timedelta(hours=2),
            raw='N0OLD>APRS:old',
            packet_type='position',
        )
        db_session.add(old_packet)

        new_packet = APRSPacket(
            from_call='N0NEW',
            to_call='APRS',
            timestamp=now - timedelta(minutes=5),
            received_at=now - timedelta(minutes=5),
            raw='N0NEW>APRS:new',
            packet_type='position',
        )
        db_session.add(new_packet)
        db_session.commit()

        result = get_recent_packets(db_session, limit=10)

        assert len(result) >= 2
        assert result[0]['from_call'] == 'N0NEW'
