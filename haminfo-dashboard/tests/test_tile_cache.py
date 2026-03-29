# tests/test_tile_cache.py
"""Tests for tile-based map caching."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


class TestGetTileCoords:
    """Tests for get_tile_coords function."""

    def test_positive_coords(self):
        """Test tile coords for positive lat/lon."""
        from haminfo_dashboard.queries import get_tile_coords

        # Portland, OR: 45.523, -122.676 -> tile (45, -123)
        assert get_tile_coords(45.523, -122.676) == (45, -123)

    def test_negative_coords(self):
        """Test tile coords for negative lat/lon."""
        from haminfo_dashboard.queries import get_tile_coords

        # Buenos Aires: -34.6, -58.4 -> tile (-35, -59)
        assert get_tile_coords(-34.6, -58.4) == (-35, -59)

    def test_exact_boundary(self):
        """Test coords exactly on tile boundary."""
        from haminfo_dashboard.queries import get_tile_coords

        # Exactly 45.0, -123.0 -> tile (45, -123)
        assert get_tile_coords(45.0, -123.0) == (45, -123)

    def test_near_zero(self):
        """Test coords near zero."""
        from haminfo_dashboard.queries import get_tile_coords

        # London area: 51.5, -0.1 -> tile (51, -1)
        assert get_tile_coords(51.5, -0.1) == (51, -1)
        # Just east of prime meridian
        assert get_tile_coords(51.5, 0.1) == (51, 0)


class TestGetTilesForBbox:
    """Tests for get_tiles_for_bbox function."""

    def test_single_tile(self):
        """Test bbox within single tile."""
        from haminfo_dashboard.queries import get_tiles_for_bbox

        # Small bbox within Portland tile
        tiles = get_tiles_for_bbox(-122.8, 45.4, -122.5, 45.6)
        assert tiles == [(45, -123)]

    def test_multiple_tiles(self):
        """Test bbox spanning multiple tiles."""
        from haminfo_dashboard.queries import get_tiles_for_bbox

        # 2x2 tile area
        tiles = get_tiles_for_bbox(-123.5, 45.2, -121.5, 46.8)
        assert set(tiles) == {
            (45, -124),
            (45, -123),
            (45, -122),
            (46, -124),
            (46, -123),
            (46, -122),
        }

    def test_bbox_order(self):
        """Test tiles are returned in consistent order."""
        from haminfo_dashboard.queries import get_tiles_for_bbox

        tiles = get_tiles_for_bbox(-123.0, 45.0, -122.0, 46.0)
        # Should be sorted by lat, then lon
        assert tiles == [(45, -123), (45, -122), (46, -123), (46, -122)]


class TestQueryTileFromDb:
    """Tests for query_tile_from_db function."""

    def test_returns_station_dicts(self):
        """Test that query returns compact station dicts."""
        from haminfo_dashboard.queries import query_tile_from_db

        # Create mock packet
        mock_packet = MagicMock()
        mock_packet.from_call = 'N0CALL'
        mock_packet.latitude = 45.5
        mock_packet.longitude = -122.6
        mock_packet.packet_type = 'position'
        mock_packet.symbol = '>'
        mock_packet.symbol_table = '/'
        mock_packet.speed = 55.0
        mock_packet.course = 180
        mock_packet.altitude = 100.0
        mock_packet.comment = 'Test station'
        mock_packet.received_at = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_packet
        ]

        result = query_tile_from_db(mock_session, 45, -123, 1, '')

        assert len(result) == 1
        assert result[0]['callsign'] == 'N0CALL'
        assert result[0]['latitude'] == 45.5
        assert result[0]['longitude'] == -122.6
        assert 'received_at' in result[0]

    def test_filters_by_tile_bounds(self):
        """Test that query filters to tile boundaries."""
        from haminfo_dashboard.queries import query_tile_from_db

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        query_tile_from_db(mock_session, 45, -123, 1, '')

        # Verify filter was called (we can't easily check the exact args)
        assert mock_session.query.return_value.filter.called


class TestGetTileStations:
    """Tests for get_tile_stations with caching."""

    @patch('haminfo_dashboard.queries.cache')
    def test_returns_cached_data_on_hit(self, mock_cache):
        """Test cache hit returns cached data without DB query."""
        from haminfo_dashboard.queries import get_tile_stations

        cached_data = [{'callsign': 'CACHED', 'latitude': 45.5}]
        mock_cache.get.return_value = cached_data

        mock_session = MagicMock()
        result = get_tile_stations(mock_session, 45, -123, 1, '')

        assert result == cached_data
        mock_session.query.assert_not_called()

    @patch('haminfo_dashboard.queries.cache')
    @patch('haminfo_dashboard.queries.query_tile_from_db')
    def test_queries_db_on_cache_miss(self, mock_query, mock_cache):
        """Test cache miss queries DB and stores result."""
        from haminfo_dashboard.queries import get_tile_stations

        mock_cache.get.return_value = None
        db_data = [{'callsign': 'FRESH', 'latitude': 45.5}]
        mock_query.return_value = db_data

        mock_session = MagicMock()
        result = get_tile_stations(mock_session, 45, -123, 1, '')

        assert result == db_data
        mock_query.assert_called_once()
        mock_cache.set.assert_called_once()

    @patch('haminfo_dashboard.queries.cache')
    @patch('haminfo_dashboard.queries.query_tile_from_db')
    def test_cache_key_format(self, mock_query, mock_cache):
        """Test cache key includes all parameters."""
        from haminfo_dashboard.queries import get_tile_stations

        mock_cache.get.return_value = None
        mock_query.return_value = []

        mock_session = MagicMock()
        get_tile_stations(mock_session, 45, -123, 1, 'weather')

        # Verify cache key format
        cache_key = mock_cache.get.call_args[0][0]
        assert 'map:tile:1:weather:45:-123' == cache_key


class TestGetMapStationsTiled:
    """Tests for get_map_stations_tiled orchestration."""

    @patch('haminfo_dashboard.queries.cache')
    @patch('haminfo_dashboard.queries.query_bbox_from_db')
    def test_queries_db_when_cache_empty(self, mock_query_bbox, mock_cache):
        """Test that DB is queried when cache is empty."""
        from haminfo_dashboard.queries import get_map_stations_tiled

        mock_cache.get.return_value = None  # All cache misses
        mock_query_bbox.return_value = []
        mock_session = MagicMock()

        get_map_stations_tiled(
            mock_session,
            bbox=(-123.5, 45.2, -121.5, 46.8),
            hours=1,
            station_type='',
            limit=500,
        )

        # Should query DB once for all tiles
        mock_query_bbox.assert_called_once()

    @patch('haminfo_dashboard.queries.cache')
    @patch('haminfo_dashboard.queries.query_bbox_from_db')
    def test_uses_cache_when_available(self, mock_query_bbox, mock_cache):
        """Test that cached data is used without DB query."""
        from haminfo_dashboard.queries import get_map_stations_tiled

        cached_station = {
            'callsign': 'CACHED',
            'latitude': 45.5,
            'longitude': -122.5,
            'received_at': '2026-03-29T12:00:00',
        }
        mock_cache.get.return_value = [cached_station]  # All cache hits
        mock_session = MagicMock()

        result = get_map_stations_tiled(
            mock_session,
            bbox=(-123.0, 45.0, -122.0, 46.0),  # 4 tiles
            hours=1,
            station_type='',
            limit=500,
        )

        # Should NOT query DB since all cached
        mock_query_bbox.assert_not_called()
        # Should return the cached station
        assert len(result) == 1
        assert result[0]['callsign'] == 'CACHED'

    @patch('haminfo_dashboard.queries.cache')
    @patch('haminfo_dashboard.queries.query_bbox_from_db')
    def test_deduplicates_by_callsign(self, mock_query_bbox, mock_cache):
        """Test that duplicate callsigns are deduplicated."""
        from haminfo_dashboard.queries import get_map_stations_tiled

        mock_cache.get.return_value = None  # Cache miss
        # Same station appears with different timestamps
        mock_query_bbox.return_value = [
            {
                'callsign': 'N0CALL',
                'latitude': 45.5,
                'longitude': -122.5,
                'received_at': '2026-03-29T12:00:00',
            },
            {
                'callsign': 'N0CALL',
                'latitude': 45.5,
                'longitude': -122.5,
                'received_at': '2026-03-29T11:00:00',
            },
        ]
        mock_session = MagicMock()

        result = get_map_stations_tiled(
            mock_session,
            bbox=(-123.0, 45.0, -122.0, 46.0),
            hours=1,
            station_type='',
            limit=500,
        )

        # Should have only one station (most recent kept)
        assert len(result) == 1
        assert result[0]['callsign'] == 'N0CALL'
        assert result[0]['received_at'] == '2026-03-29T12:00:00'

    @patch('haminfo_dashboard.queries.cache')
    @patch('haminfo_dashboard.queries.query_bbox_from_db')
    def test_filters_to_exact_bbox(self, mock_query_bbox, mock_cache):
        """Test that results are filtered to exact bbox."""
        from haminfo_dashboard.queries import get_map_stations_tiled

        mock_cache.get.return_value = None
        mock_query_bbox.return_value = [
            {
                'callsign': 'INSIDE',
                'latitude': 45.5,
                'longitude': -122.5,
                'received_at': '2026-03-29T12:00:00',
            },
            {
                'callsign': 'OUTSIDE',
                'latitude': 45.1,
                'longitude': -122.9,
                'received_at': '2026-03-29T12:00:00',
            },
        ]
        mock_session = MagicMock()

        result = get_map_stations_tiled(
            mock_session,
            bbox=(-122.7, 45.4, -122.3, 45.7),  # Tight bbox
            hours=1,
            station_type='',
            limit=500,
        )

        assert len(result) == 1
        assert result[0]['callsign'] == 'INSIDE'

    @patch('haminfo_dashboard.queries.cache')
    @patch('haminfo_dashboard.queries.query_bbox_from_db')
    def test_respects_limit(self, mock_query_bbox, mock_cache):
        """Test that limit is applied to results."""
        from haminfo_dashboard.queries import get_map_stations_tiled

        mock_cache.get.return_value = None
        mock_query_bbox.return_value = [
            {
                'callsign': f'CALL{i}',
                'latitude': 45.5,
                'longitude': -122.5,
                'received_at': f'2026-03-29T{12 - i:02d}:00:00',
            }
            for i in range(10)
        ]
        mock_session = MagicMock()

        result = get_map_stations_tiled(
            mock_session,
            bbox=(-123.0, 45.0, -122.0, 46.0),
            hours=1,
            station_type='',
            limit=3,
        )

        assert len(result) == 3

    @patch('haminfo_dashboard.queries.cache')
    @patch('haminfo_dashboard.queries.query_bbox_from_db')
    def test_limits_tiles_per_request(self, mock_query_bbox, mock_cache):
        """Test that too many tiles are truncated."""
        from haminfo_dashboard.queries import (
            get_map_stations_tiled,
            MAX_TILES_PER_REQUEST,
        )

        mock_cache.get.return_value = None
        mock_query_bbox.return_value = []
        mock_session = MagicMock()

        # Request huge bbox that would span many tiles
        get_map_stations_tiled(
            mock_session,
            bbox=(-180.0, -90.0, 180.0, 90.0),  # Whole world
            hours=1,
            station_type='',
            limit=500,
        )

        # Should still work (just limited)
        mock_query_bbox.assert_called_once()

    @patch('haminfo_dashboard.queries.cache')
    @patch('haminfo_dashboard.queries.query_bbox_from_db')
    def test_caches_results_per_tile(self, mock_query_bbox, mock_cache):
        """Test that results are cached per tile."""
        from haminfo_dashboard.queries import get_map_stations_tiled

        mock_cache.get.return_value = None  # All cache misses
        mock_query_bbox.return_value = [
            {
                'callsign': 'N0CALL',
                'latitude': 45.5,
                'longitude': -122.5,
                'received_at': '2026-03-29T12:00:00',
            },
        ]
        mock_session = MagicMock()

        get_map_stations_tiled(
            mock_session,
            bbox=(-123.0, 45.0, -122.0, 46.0),  # 4 tiles
            hours=1,
            station_type='',
            limit=500,
        )

        # Should cache each tile (4 tiles)
        assert mock_cache.set.call_count == 4
