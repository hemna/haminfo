"""Unit tests for APRS position query functions."""

from __future__ import annotations

from datetime import datetime, timedelta

from haminfo.db.models.aprs_packet import APRSPacket
from haminfo.db import db as haminfo_db


def _make_packet(
    db_session,
    from_call: str,
    lat: float | None = 34.9463,
    lon: float | None = -123.7612,
    packet_type: str = 'position',
    timestamp: datetime | None = None,
    **kwargs,
) -> APRSPacket:
    """Helper to create and persist an APRSPacket for testing."""
    if timestamp is None:
        timestamp = datetime.utcnow()
    pkt = APRSPacket(
        from_call=from_call,
        to_call=kwargs.get('to_call', 'APRS'),
        path=kwargs.get('path', 'WIDE1-1'),
        raw=kwargs.get('raw', f'{from_call}>APRS:!pos'),
        packet_type=packet_type,
        latitude=lat,
        longitude=lon,
        altitude=kwargs.get('altitude'),
        course=kwargs.get('course'),
        speed=kwargs.get('speed'),
        symbol=kwargs.get('symbol', '-'),
        symbol_table=kwargs.get('symbol_table', '/'),
        comment=kwargs.get('comment', ''),
        timestamp=timestamp,
        received_at=kwargs.get('received_at', datetime.utcnow()),
    )
    db_session.add(pkt)
    db_session.flush()
    return pkt


class TestFindLatestPositionsByCallsigns:
    """Tests for find_latest_positions_by_callsigns()."""

    def test_single_callsign_found(self, db_session):
        _make_packet(db_session, 'N0CALL')
        results = haminfo_db.find_latest_positions_by_callsigns(db_session, ['N0CALL'])
        assert len(results) == 1
        assert results[0].from_call == 'N0CALL'

    def test_single_callsign_not_found(self, db_session):
        results = haminfo_db.find_latest_positions_by_callsigns(
            db_session, ['NONEXIST']
        )
        assert len(results) == 0

    def test_multiple_callsigns_partial_match(self, db_session):
        _make_packet(db_session, 'W3ADO')
        _make_packet(db_session, 'K3ABC')
        results = haminfo_db.find_latest_positions_by_callsigns(
            db_session, ['W3ADO', 'K3ABC', 'NONEXIST']
        )
        found_calls = {r.from_call for r in results}
        assert found_calls == {'W3ADO', 'K3ABC'}

    def test_case_insensitive_matching(self, db_session):
        _make_packet(db_session, 'W3ADO')
        results = haminfo_db.find_latest_positions_by_callsigns(db_session, ['w3ado'])
        assert len(results) == 1
        assert results[0].from_call == 'W3ADO'

    def test_returns_most_recent_position(self, db_session):
        old_time = datetime.utcnow() - timedelta(hours=2)
        new_time = datetime.utcnow()
        _make_packet(
            db_session,
            'N0CALL',
            lat=10.0,
            lon=20.0,
            timestamp=old_time,
            comment='old',
        )
        _make_packet(
            db_session,
            'N0CALL',
            lat=30.0,
            lon=40.0,
            timestamp=new_time,
            comment='new',
        )
        results = haminfo_db.find_latest_positions_by_callsigns(db_session, ['N0CALL'])
        assert len(results) == 1
        assert results[0].comment == 'new'
        assert results[0].latitude == 30.0

    def test_excludes_packets_without_position(self, db_session):
        _make_packet(db_session, 'NOPOS', lat=None, lon=None)
        _make_packet(db_session, 'HASPOS', lat=10.0, lon=20.0)
        results = haminfo_db.find_latest_positions_by_callsigns(
            db_session, ['NOPOS', 'HASPOS']
        )
        found_calls = {r.from_call for r in results}
        assert 'NOPOS' not in found_calls
        assert 'HASPOS' in found_calls

    def test_empty_callsigns_list(self, db_session):
        results = haminfo_db.find_latest_positions_by_callsigns(db_session, [])
        assert results == []


class TestFindLatestPositionByCallsign:
    """Tests for find_latest_position_by_callsign()."""

    def test_found(self, db_session):
        _make_packet(db_session, 'N0CALL')
        result = haminfo_db.find_latest_position_by_callsign(db_session, 'N0CALL')
        assert result is not None
        assert result.from_call == 'N0CALL'

    def test_not_found(self, db_session):
        result = haminfo_db.find_latest_position_by_callsign(db_session, 'NONEXIST')
        assert result is None


class TestCleanAprsPackets:
    """Tests for clean_aprs_packets()."""

    def test_deletes_old_packets(self, db_session):
        old_time = datetime.utcnow() - timedelta(days=31)
        _make_packet(
            db_session,
            'OLD',
            timestamp=old_time,
            received_at=old_time,
        )
        _make_packet(db_session, 'NEW')
        db_session.flush()

        count = haminfo_db.clean_aprs_packets(db_session, days=30)
        assert count == 1

        # Only the recent packet should remain
        remaining = db_session.query(APRSPacket).all()
        assert len(remaining) == 1
        assert remaining[0].from_call == 'NEW'

    def test_deletes_nothing_when_all_recent(self, db_session):
        _make_packet(db_session, 'A')
        _make_packet(db_session, 'B')
        db_session.flush()

        count = haminfo_db.clean_aprs_packets(db_session, days=30)
        assert count == 0
        assert db_session.query(APRSPacket).count() == 2

    def test_custom_days_parameter(self, db_session):
        # Packet 8 days old — should survive 30-day retention but not 7-day
        eight_days_ago = datetime.utcnow() - timedelta(days=8)
        _make_packet(
            db_session,
            'MIDAGE',
            timestamp=eight_days_ago,
            received_at=eight_days_ago,
        )
        _make_packet(db_session, 'FRESH')
        db_session.flush()

        count = haminfo_db.clean_aprs_packets(db_session, days=7)
        assert count == 1

        remaining = db_session.query(APRSPacket).all()
        assert len(remaining) == 1
        assert remaining[0].from_call == 'FRESH'

    def test_returns_zero_on_empty_table(self, db_session):
        count = haminfo_db.clean_aprs_packets(db_session, days=30)
        assert count == 0


class TestGetAprsPacketStats:
    """Tests for get_aprs_packet_stats()."""

    def test_returns_correct_counts(self, db_session):
        _make_packet(db_session, 'POS1', packet_type='position')
        _make_packet(db_session, 'POS2', packet_type='position')
        _make_packet(db_session, 'WX1', packet_type='weather')
        _make_packet(db_session, 'MSG1', packet_type='message')
        db_session.flush()

        stats = haminfo_db.get_aprs_packet_stats(db_session)
        assert stats['total'] == 4
        assert stats['position'] == 2
        assert stats['weather'] == 1
        assert stats['message'] == 1
        assert stats['other'] == 0
        assert stats['unique_callsigns'] == 4

    def test_last_24h_counts_recent_only(self, db_session):
        old_time = datetime.utcnow() - timedelta(hours=25)
        _make_packet(
            db_session,
            'OLD',
            received_at=old_time,
            timestamp=old_time,
        )
        _make_packet(db_session, 'RECENT')
        db_session.flush()

        stats = haminfo_db.get_aprs_packet_stats(db_session)
        assert stats['total'] == 2
        assert stats['last_24h'] == 1

    def test_empty_table_returns_zeros(self, db_session):
        stats = haminfo_db.get_aprs_packet_stats(db_session)
        assert stats['total'] == 0
        assert stats['position'] == 0
        assert stats['weather'] == 0
        assert stats['message'] == 0
        assert stats['other'] == 0
        assert stats['unique_callsigns'] == 0
        assert stats['last_24h'] == 0

    def test_unknown_packet_type_counted_as_other(self, db_session):
        _make_packet(db_session, 'X1', packet_type='telemetry')
        _make_packet(db_session, 'X2', packet_type='status')
        _make_packet(db_session, 'P1', packet_type='position')
        db_session.flush()

        stats = haminfo_db.get_aprs_packet_stats(db_session)
        assert stats['total'] == 3
        assert stats['position'] == 1
        assert stats['other'] == 2
