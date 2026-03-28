# tests/conftest.py
"""Test fixtures for haminfo-dashboard."""

import pytest
from flask import Flask
from unittest.mock import MagicMock, patch


@pytest.fixture
def app():
    """Create test Flask application."""
    from haminfo_dashboard.app import create_app

    # Mock the haminfo config loading
    with patch('haminfo_dashboard.app._load_haminfo_config'):
        app = create_app()
        app.config['TESTING'] = True
        yield app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = MagicMock()
    session.query.return_value.filter.return_value.scalar.return_value = 0
    session.query.return_value.filter.return_value.all.return_value = []
    session.query.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
    return session
