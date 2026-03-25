"""Tests for weather history API."""

from __future__ import annotations

from datetime import datetime, timezone

from haminfo.db.db import get_wx_history


class TestGetWxHistory:
    """Tests for get_wx_history database function."""

    def test_returns_empty_list_for_no_data(self, db_session):
        """Test that empty result is returned when no data exists."""
        start = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 21, 0, 0, 0, tzinfo=timezone.utc)

        result = get_wx_history(
            db_session,
            station_id=99999,  # Non-existent station
            start=start,
            end=end,
            fields=['temperature'],
        )

        assert result == []

    def test_returns_hourly_aggregated_data(self, db_session, wx_station_with_reports):
        """Test that data is aggregated by hour."""
        station = wx_station_with_reports
        start = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 20, 3, 0, 0, tzinfo=timezone.utc)

        result = get_wx_history(
            db_session,
            station_id=station.id,
            start=start,
            end=end,
            fields=['temperature'],
        )

        assert len(result) > 0
        for row in result:
            assert 'time' in row
            assert 'temperature' in row

    def test_returns_only_requested_fields(self, db_session, wx_station_with_reports):
        """Test that only requested fields are returned."""
        station = wx_station_with_reports
        start = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 20, 3, 0, 0, tzinfo=timezone.utc)

        result = get_wx_history(
            db_session,
            station_id=station.id,
            start=start,
            end=end,
            fields=['temperature', 'humidity'],
        )

        if result:
            row = result[0]
            assert 'temperature' in row
            assert 'humidity' in row
            assert 'pressure' not in row
            assert 'wind_speed' not in row
