"""Tests for the mail CLI (thin REST client)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from mailhub.mail_cli import (
    MailCLIError,
    _validate_loopback_url,
    _get_token,
    _make_client,
    _handle_response,
    _output,
    cmd_accounts,
    cmd_folders,
    cmd_search,
    cmd_get,
    cmd_send,
    cmd_draft,
    main,
)


class MockArgs:
    """Mock argparse.Namespace for testing."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestValidateLoopbackUrl:
    def test_valid_localhost(self):
        assert _validate_loopback_url("http://localhost:8787") == "http://localhost:8787"
    
    def test_valid_127(self):
        assert _validate_loopback_url("http://127.0.0.1:8787") == "http://127.0.0.1:8787"
    
    def test_valid_ipv6_loopback(self):
        assert _validate_loopback_url("http://[::1]:8787") == "http://[::1]:8787"
    
    def test_invalid_external(self):
        with pytest.raises(MailCLIError) as exc:
            _validate_loopback_url("http://example.com:8787")
        assert "loopback" in str(exc.value)
        assert exc.value.exit_code == 1
    
    def test_invalid_non_loopback_ip(self):
        with pytest.raises(MailCLIError) as exc:
            _validate_loopback_url("http://192.168.1.1:8787")
        assert "loopback" in str(exc.value)


class TestHandleResponse:
    def test_success_json(self):
        mock_resp = Mock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"key": "value"}
        
        result = _handle_response(mock_resp)
        assert result == {"key": "value"}
    
    def test_success_list(self):
        mock_resp = Mock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"id": "1"}, {"id": "2"}]
        
        result = _handle_response(mock_resp)
        assert result == [{"id": "1"}, {"id": "2"}]
    
    def test_401_unauthorized(self):
        mock_resp = Mock(spec=httpx.Response)
        mock_resp.status_code = 401
        
        with pytest.raises(MailCLIError) as exc:
            _handle_response(mock_resp)
        assert "Authentication failed" in str(exc.value)
        assert exc.value.exit_code == 1
    
    def test_403_forbidden(self):
        mock_resp = Mock(spec=httpx.Response)
        mock_resp.status_code = 403
        mock_resp.json.return_value = {"error": "Full scope required"}
        
        with pytest.raises(MailCLIError) as exc:
            _handle_response(mock_resp)
        assert "Access denied" in str(exc.value)
        assert "Full scope required" in str(exc.value)
        assert exc.value.exit_code == 1
    
    def test_500_server_error(self):
        mock_resp = Mock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        
        with pytest.raises(MailCLIError) as exc:
            _handle_response(mock_resp)
        assert "Server error" in str(exc.value)
        assert exc.value.exit_code == 1
    
    def test_400_bad_request(self):
        mock_resp = Mock(spec=httpx.Response)
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"error": "Invalid query"}
        
        with pytest.raises(MailCLIError) as exc:
            _handle_response(mock_resp)
        assert "Request failed" in str(exc.value)
        assert "Invalid query" in str(exc.value)


class TestOutput:
    def test_json_output(self, capsys):
        _output({"key": "value"}, as_json=True)
        out = capsys.readouterr().out
        assert '"key": "value"' in out
    
    def test_text_output_dict(self, capsys):
        _output({"key": "value", "num": 42}, as_json=False)
        out = capsys.readouterr().out
        assert "key: value" in out
        assert "num: 42" in out
    
    def test_text_output_list(self, capsys):
        _output([{"a": 1}, {"b": 2}], as_json=False)
        out = capsys.readouterr().out
        assert "a: 1" in out
        assert "b: 2" in out


class TestCommands:
    """Test CLI commands with mocked HTTP client."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock httpx.Client."""
        with patch("mailhub.mail_cli.httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            yield mock_client
    
    @pytest.fixture
    def mock_tokens(self):
        """Mock token loading."""
        with patch("mailhub.mail_cli._load_tokens") as mock:
            mock.return_value = {"ro_token": "ro-token-123", "full_token": "full-token-456"}
            yield mock
    
    def test_cmd_accounts(self, mock_client, mock_tokens, capsys):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"alias": "personal", "provider": "gmail", "email": "me@gmail.com", "has_refresh_token": True, "has_access_token": True}
        ]
        mock_client.get.return_value = mock_resp
        
        args = MockArgs(url="http://127.0.0.1:8787", token=None, ro=False, json=False, config=None, state=None)
        
        result = cmd_accounts(args, None, None)
        
        assert result == 0
        mock_client.get.assert_called_once_with("/accounts")
        out = capsys.readouterr().out
        assert "personal" in out
    
    def test_cmd_accounts_json(self, mock_client, mock_tokens, capsys):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"alias": "test"}]
        mock_client.get.return_value = mock_resp
        
        args = MockArgs(url="http://127.0.0.1:8787", token=None, ro=False, json=True, config=None, state=None)
        
        result = cmd_accounts(args, None, None)
        
        assert result == 0
        out = capsys.readouterr().out
        assert '"alias": "test"' in out
    
    def test_cmd_folders(self, mock_client, mock_tokens):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"folders": [{"id": "INBOX", "name": "Inbox"}]}
        mock_client.get.return_value = mock_resp
        
        args = MockArgs(url="http://127.0.0.1:8787", token=None, ro=False, json=False, config=None, state=None, account="personal")
        
        result = cmd_folders(args, None, None)
        
        assert result == 0
        mock_client.get.assert_called_once_with("/accounts/personal/folders")
    
    def test_cmd_search(self, mock_client, mock_tokens):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"messages": [{"id": "1"}], "next_page_token": "next"}
        mock_client.get.return_value = mock_resp
        
        args = MockArgs(
            url="http://127.0.0.1:8787", token=None, ro=False, json=False,
            config=None, state=None, account="personal", query="test", max_results=25, page_token="abc"
        )
        
        result = cmd_search(args, None, None)
        
        assert result == 0
        mock_client.get.assert_called_once_with(
            "/accounts/personal/messages",
            params={"q": "test", "max_results": 25, "page_token": "abc"}
        )
    
    def test_cmd_search_no_page_token(self, mock_client, mock_tokens):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"messages": []}
        mock_client.get.return_value = mock_resp
        
        args = MockArgs(
            url="http://127.0.0.1:8787", token=None, ro=False, json=False,
            config=None, state=None, account="personal", query="test", max_results=50, page_token=None
        )
        
        result = cmd_search(args, None, None)
        
        assert result == 0
        # page_token should not be in params when None
        call_args = mock_client.get.call_args
        assert "page_token" not in call_args.kwargs["params"]
    
    def test_cmd_get(self, mock_client, mock_tokens):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "msg-123", "subject": "Hello"}
        mock_client.get.return_value = mock_resp
        
        args = MockArgs(url="http://127.0.0.1:8787", token=None, ro=False, json=False, config=None, state=None, account="personal", message_id="msg-123")
        
        result = cmd_get(args, None, None)
        
        assert result == 0
        mock_client.get.assert_called_once_with("/accounts/personal/messages/msg-123")
    
    def test_cmd_send_requires_confirm(self, mock_client, mock_tokens):
        args = MockArgs(
            url="http://127.0.0.1:8787", token=None, ro=False, json=False,
            config=None, state=None, account="personal",
            to=["test@example.com"], cc=None, bcc=None,
            subject="Test", text_body="Body", html_body=None,
            html=False, body_file=None, in_reply_to=None, references=None,
            confirm=False  # Not confirmed
        )
        
        with pytest.raises(MailCLIError) as exc:
            cmd_send(args, None, None)
        assert "requires --confirm" in str(exc.value)
        assert exc.value.exit_code == 1
    
    def test_cmd_send_success(self, mock_client, mock_tokens):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "sent-123", "thread_id": "thread-456"}
        mock_client.post.return_value = mock_resp
        
        args = MockArgs(
            url="http://127.0.0.1:8787", token=None, ro=False, json=False,
            config=None, state=None, account="personal",
            to=["test@example.com"], cc=["cc@example.com"], bcc=None,
            subject="Test", text_body="Body", html_body=None,
            html=False, body_file=None, in_reply_to=None, references=None,
            confirm=True
        )
        
        result = cmd_send(args, None, None)
        
        assert result == 0
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args.args[0] == "/accounts/personal/send"
        payload = call_args.kwargs["json"]
        assert payload["to"] == ["test@example.com"]
        assert payload["cc"] == ["cc@example.com"]
        assert payload["confirm"] is True
    
    def test_cmd_send_requires_full_token(self, mock_client, mock_tokens):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        
        # Using ro token (default when --ro is passed)
        args = MockArgs(
            url="http://127.0.0.1:8787", token=None, ro=True, json=False,
            config=None, state=None, account="personal",
            to=["test@example.com"], cc=None, bcc=None,
            subject="Test", text_body="Body", html_body=None,
            html=False, body_file=None, in_reply_to=None, references=None,
            confirm=True
        )
        
        with pytest.raises(MailCLIError) as exc:
            cmd_send(args, None, None)
        assert "full-access token" in str(exc.value)
    
    def test_cmd_draft_success(self, mock_client, mock_tokens):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "draft-123"}
        mock_client.post.return_value = mock_resp
        
        args = MockArgs(
            url="http://127.0.0.1:8787", token=None, ro=False, json=False,
            config=None, state=None, account="personal",
            to=["test@example.com"], cc=None, bcc=None,
            subject="Draft", text_body="Body", html_body=None,
            html=False, body_file=None, in_reply_to=None, references=None,
        )
        
        result = cmd_draft(args, None, None)
        
        assert result == 0
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args.args[0] == "/accounts/personal/draft"
        payload = call_args.kwargs["json"]
        assert payload["to"] == ["test@example.com"]
        assert "confirm" not in payload  # draft doesn't have confirm
    
    def test_cmd_draft_requires_full_token(self, mock_client, mock_tokens):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        
        args = MockArgs(
            url="http://127.0.0.1:8787", token=None, ro=True, json=False,
            config=None, state=None, account="personal",
            to=["test@example.com"], cc=None, bcc=None,
            subject="Draft", text_body="Body", html_body=None,
            html=False, body_file=None, in_reply_to=None, references=None,
        )
        
        with pytest.raises(MailCLIError) as exc:
            cmd_draft(args, None, None)
        assert "full-access token" in str(exc.value)


class TestGetToken:
    def test_explicit_token(self):
        args = MockArgs(token="explicit-token", ro=False)
        with patch("mailhub.mail_cli._load_tokens") as mock_load:
            mock_load.return_value = {"ro_token": "ro", "full_token": "full"}
            token = _get_token(args, None, None)
            assert token == "explicit-token"
    
    def test_ro_flag(self):
        args = MockArgs(token=None, ro=True)
        with patch("mailhub.mail_cli._load_tokens") as mock_load:
            mock_load.return_value = {"ro_token": "ro-token", "full_token": "full-token"}
            token = _get_token(args, None, None)
            assert token == "ro-token"
    
    def test_default_full_token(self):
        args = MockArgs(token=None, ro=False)
        with patch("mailhub.mail_cli._load_tokens") as mock_load:
            mock_load.return_value = {"ro_token": "ro-token", "full_token": "full-token"}
            token = _get_token(args, None, None)
            assert token == "full-token"
    
    def test_ro_token_missing(self):
        args = MockArgs(token=None, ro=True)
        with patch("mailhub.mail_cli._load_tokens") as mock_load:
            mock_load.return_value = {"ro_token": "", "full_token": "full-token"}
            with pytest.raises(MailCLIError) as exc:
                _get_token(args, None, None)
            assert "read-only token configured" in str(exc.value)


class TestMain:
    """Integration-style tests for main entry point."""
    
    @patch("mailhub.mail_cli.load_config")
    @patch("mailhub.mail_cli.cmd_accounts")
    def test_main_accounts(self, mock_cmd, mock_load_config):
        mock_cmd.return_value = 0
        
        with patch("sys.argv", ["mail", "accounts"]):
            with patch("mailhub.mail_cli.config_path", return_value=Path("/tmp/config.toml")):
                with patch("mailhub.mail_cli.state_path", return_value=Path("/tmp/credentials.json")):
                    with patch("pathlib.Path.exists", return_value=True):
                        result = main(["--url", "http://127.0.0.1:8787", "accounts"])
        
        assert result == 0
        mock_cmd.assert_called_once()
    
    @patch("mailhub.mail_cli.load_config")
    def test_main_missing_config(self, mock_load_config, capsys):
        mock_load_config.side_effect = FileNotFoundError()
        
        with patch("mailhub.mail_cli.config_path", return_value=Path("/tmp/missing.toml")):
            result = main(["--url", "http://127.0.0.1:8787", "accounts"])
        
        assert result == 2
        err = capsys.readouterr().err
        assert "configuration not found" in err
    
    @patch("mailhub.mail_cli.load_config")
    def test_main_invalid_url(self, mock_load_config, capsys):
        with patch("mailhub.mail_cli.config_path", return_value=Path("/tmp/config.toml")):
            with patch("pathlib.Path.exists", return_value=True):
                result = main(["--url", "http://evil.com", "accounts"])
        
        assert result == 1
        err = capsys.readouterr().err
        assert "loopback" in err
    
    @patch("mailhub.mail_cli.load_config")
    @patch("mailhub.mail_cli.cmd_accounts")
    def test_main_connection_error(self, mock_cmd, mock_load_config, capsys):
        import httpx
        mock_cmd.side_effect = httpx.ConnectError("Connection refused")
        
        with patch("mailhub.mail_cli.config_path", return_value=Path("/tmp/config.toml")):
            with patch("pathlib.Path.exists", return_value=True):
                result = main(["--url", "http://127.0.0.1:8787", "accounts"])
        
        assert result == 1
        err = capsys.readouterr().err
        assert "cannot connect" in err
