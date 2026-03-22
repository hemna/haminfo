"""Tests for RepeaterBook fetcher authentication."""

from unittest.mock import patch, MagicMock


class TestBuildRepeaterBookHeaders:
    """Test header construction for RepeaterBook API."""

    @patch('haminfo.cmds.fetch_repeaterbook.CONF')
    def test_auth_header_added_when_token_configured(self, mock_conf):
        """X-RB-App-Token header should be added when api_token is set."""
        from haminfo.cmds.fetch_repeaterbook import _build_repeaterbook_headers

        mock_conf.repeaterbook.api_token = 'app_test-token-123'

        headers = _build_repeaterbook_headers()

        assert 'X-RB-App-Token' in headers
        assert headers['X-RB-App-Token'] == 'app_test-token-123'

    @patch('haminfo.cmds.fetch_repeaterbook.CONF')
    def test_no_auth_header_when_token_empty(self, mock_conf):
        """No X-RB-App-Token header when api_token is empty."""
        from haminfo.cmds.fetch_repeaterbook import _build_repeaterbook_headers

        mock_conf.repeaterbook.api_token = ''

        headers = _build_repeaterbook_headers()

        assert 'X-RB-App-Token' not in headers

    @patch('haminfo.cmds.fetch_repeaterbook.CONF')
    def test_user_agent_is_repeat(self, mock_conf):
        """User-Agent header should be REPEAT/1.0."""
        from haminfo.cmds.fetch_repeaterbook import _build_repeaterbook_headers

        mock_conf.repeaterbook.api_token = ''

        headers = _build_repeaterbook_headers()

        assert 'User-Agent' in headers
        assert headers['User-Agent'] == 'REPEAT/1.0'


class TestRepeaterBookAuth:
    """Test RepeaterBook API authentication in fetch_repeaters."""

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

        # Access the underlying function to bypass rate limiting
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

    @patch('haminfo.cmds.fetch_repeaterbook.CONF')
    @patch('haminfo.cmds.fetch_repeaterbook.requests.get')
    def test_request_includes_timeout(self, mock_get, mock_conf):
        """Request should include a timeout to prevent hangs."""
        import haminfo.cmds.fetch_repeaterbook as rb_module

        mock_conf.repeaterbook.api_token = ''
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"count": 0, "results": []}'
        mock_get.return_value = mock_response

        rb_module.fetch_repeaters.__wrapped__.__wrapped__(
            'http://example.com/api', None, fetch_only=True
        )

        # Verify timeout was passed
        call_args = mock_get.call_args
        assert call_args.kwargs.get('timeout') == 30
