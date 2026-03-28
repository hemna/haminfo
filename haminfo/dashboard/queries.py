# haminfo/dashboard/queries.py
"""Database query helpers for dashboard."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def get_dashboard_stats(session: Session) -> dict:
    """Get summary statistics for dashboard."""
    return {
        'total_packets_24h': 0,
        'unique_stations': 0,
        'countries': 0,
        'weather_stations': 0,
    }
