"""Tests for RepeaterBook fetcher authentication."""

import pytest
from unittest.mock import patch, MagicMock


class TestRepeaterBookAuth:
    """Test RepeaterBook API authentication."""

    @patch(
        'haminfo.cmds.fetch_repeaterbook.limits', lambda *args, **kwargs: lambda f: f
    )
    @patch('haminfo.cmds.fetch_repeaterbook.CONF')
    @patch('haminfo.cmds.fetch_repeaterbook.requests.get')
    def test_auth_header_added_when_token_configured(self, mock_get, mock_conf):
        """Authorization header should be added when api_token is set."""
        # Need to reimport after patching the decorator
        import importlib
        import haminfo.cmds.fetch_repeaterbook as rb_module

        mock_conf.repeaterbook.api_token = 'test-token-123'
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"count": 0, "results": []}'
        mock_get.return_value = mock_response

        # Call the underlying function directly to bypass rate limiting
        # The actual logic we want to test is the header construction
        rb_module.fetch_repeaters.__wrapped__.__wrapped__(
            'http://example.com/api', None, fetch_only=True
        )

        # Verify Authorization header was included
        call_args = mock_get.call_args
        headers = call_args.kwargs.get('headers') or call_args[1].get('headers', {})
        assert 'Authorization' in headers
        assert headers['Authorization'] == 'Bearer test-token-123'

    @patch('haminfo.cmds.fetch_repeaterbook.CONF')
    @patch('haminfo.cmds.fetch_repeaterbook.requests.get')
    def test_no_auth_header_when_token_empty(self, mock_get, mock_conf):
        """No Authorization header when api_token is empty."""
        import haminfo.cmds.fetch_repeaterbook as rb_module

        mock_conf.repeaterbook.api_token = ''
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"count": 0, "results": []}'
        mock_get.return_value = mock_response

        # Call the underlying function directly to bypass rate limiting
        rb_module.fetch_repeaters.__wrapped__.__wrapped__(
            'http://example.com/api', None, fetch_only=True
        )

        call_args = mock_get.call_args
        headers = call_args.kwargs.get('headers') or call_args[1].get('headers', {})
        assert 'Authorization' not in headers

    @patch('haminfo.cmds.fetch_repeaterbook.CONF')
    @patch('haminfo.cmds.fetch_repeaterbook.requests.get')
    def test_user_agent_always_included(self, mock_get, mock_conf):
        """User-Agent header should always be included."""
        import haminfo.cmds.fetch_repeaterbook as rb_module

        mock_conf.repeaterbook.api_token = ''
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"count": 0, "results": []}'
        mock_get.return_value = mock_response

        rb_module.fetch_repeaters.__wrapped__.__wrapped__(
            'http://example.com/api', None, fetch_only=True
        )

        call_args = mock_get.call_args
        headers = call_args.kwargs.get('headers') or call_args[1].get('headers', {})
        assert 'User-Agent' in headers
        assert 'haminfo' in headers['User-Agent']

    @patch('haminfo.cmds.fetch_repeaterbook.CONF')
    @patch('haminfo.cmds.fetch_repeaterbook.requests.get')
    def test_returns_zero_on_auth_failure(self, mock_get, mock_conf):
        """Should return 0 when authentication fails (401)."""
        import haminfo.cmds.fetch_repeaterbook as rb_module

        mock_conf.repeaterbook.api_token = 'invalid-token'
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = '{"error": "auth_missing"}'
        mock_get.return_value = mock_response

        result = rb_module.fetch_repeaters.__wrapped__.__wrapped__(
            'http://example.com/api', None, fetch_only=True
        )

        assert result == 0

    @patch('haminfo.cmds.fetch_repeaterbook.CONF')
    @patch('haminfo.cmds.fetch_repeaterbook.requests.get')
    def test_returns_zero_on_forbidden(self, mock_get, mock_conf):
        """Should return 0 when access is forbidden (403)."""
        import haminfo.cmds.fetch_repeaterbook as rb_module

        mock_conf.repeaterbook.api_token = 'expired-token'
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = '{"error": "forbidden"}'
        mock_get.return_value = mock_response

        result = rb_module.fetch_repeaters.__wrapped__.__wrapped__(
            'http://example.com/api', None, fetch_only=True
        )

        assert result == 0
