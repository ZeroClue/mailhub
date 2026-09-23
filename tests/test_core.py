"""Unit tests for mailhub.core module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mailhub.config import Account, Config
from mailhub.core import (
    Core,
    CoreError,
    RetryPolicy,
    SendDenied,
    SendPolicy,
    _state_path,
)
from mailhub.oauth import ReauthNeeded
from mailhub.store import CredentialStore


class TestStatePath:
    def test_state_path_from_config_file(self, tmp_path):
        config_file = tmp_path / "config.toml"
        result = _state_path(config_file)
        # _state_path returns parent/mailhub/credentials.json
        assert result == tmp_path / "mailhub" / "credentials.json"


class TestRetryPolicy:
    def test_defaults(self):
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.base_delay == 1.0
        assert policy.max_delay == 30.0

    def test_custom_values(self):
        policy = RetryPolicy(max_attempts=5, base_delay=2.0, max_delay=60.0)
        assert policy.max_attempts == 5
        assert policy.base_delay == 2.0
        assert policy.max_delay == 60.0


class TestSendPolicy:
    def test_defaults(self):
        policy = SendPolicy()
        assert policy.allowlist == ()
        assert policy.allow_anywhere is False

    def test_with_allowlist(self):
        policy = SendPolicy(allowlist=("*.example.com",))
        assert policy.allowlist == ("*.example.com",)

    def test_allow_anywhere(self):
        policy = SendPolicy(allow_anywhere=True)
        assert policy.allow_anywhere is True


class TestCore:
    @pytest.fixture
    def temp_config(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("""[accounts.personal]
provider = "gmail"
capabilities = ["mail"]
""")
        return config_file

    @pytest.fixture
    def temp_state(self, tmp_path):
        state_file = tmp_path / "credentials.json"
        state_file.parent.mkdir(exist_ok=True)
        state_file.write_text("{}")
        return state_file

    @pytest.fixture
    def core(self, temp_config, temp_state):
        core = Core(config_file=temp_config, state_file=temp_state)
        # Replace _get_adapter to return mock adapters
        mock_gmail = MagicMock()
        mock_gmail.send.return_value = {"id": "msg123"}
        mock_gmail.draft.return_value = {"id": "draft123"}
        mock_gmail.profile.return_value = {"email": "test@gmail.com"}
        
        mock_graph = MagicMock()
        mock_graph.send.return_value = {"id": "msg123"}
        mock_graph.draft.return_value = {"id": "draft123"}
        mock_graph.profile.return_value = {"email": "test@outlook.com"}
        
        def mock_get_adapter(provider):
            if provider == "gmail":
                return mock_gmail
            elif provider == "graph":
                return mock_graph
            raise CoreError(f"unsupported provider: {provider}")
        
        core._get_adapter = mock_get_adapter
        yield core

    def test_initializes_with_config_and_store(self, core, temp_config, temp_state):
        assert core._config is not None
        assert core._store is not None

    def test_loads_accounts_from_config(self, core):
        accounts = core._config.accounts
        assert len(accounts) == 1
        assert accounts[0].alias == "personal"
        assert accounts[0].provider == "gmail"

    def test_send_denied_without_confirm(self, core):
        # Confirm is checked first (fail fast)
        with pytest.raises(SendDenied, match="send requires confirm=true"):
            core.send("personal", to=["test@example.com"], subject="Test", confirm=False)

    def test_send_denied_without_allowlist(self, core):
        # With confirm=true but no allowlist, should fail on allowlist
        with pytest.raises(SendDenied, match="allowlist"):
            core.send("personal", to=["test@example.com"], subject="Test", confirm=True)

    def test_send_allowed_with_allow_anywhere(self, core):
        # allow_anywhere=True should skip allowlist
        core._send_policy = SendPolicy(allow_anywhere=True)
        result = core.send("personal", to=["test@example.com"], subject="Test", confirm=True)
        assert result.get("id") == "msg123"

    def test_send_allowed_with_matching_allowlist(self, core):
        # Matching allowlist should allow send
        core._send_policy = SendPolicy(allowlist=("*@example.com",))
        result = core.send("personal", to=["test@example.com"], subject="Test", confirm=True)
        assert result.get("id") == "msg123"

    def test_draft_does_not_require_confirm(self, core):
        # Draft should not require confirm
        result = core.draft("personal", to=["test@example.com"], subject="Test")
        assert result.get("id") == "draft123"

    def test_audit_log_created(self, core, tmp_path):
        audit_file = tmp_path / "audit.jsonl"
        core._audit_path = audit_file
        core._audit("personal", "send", {"to": ["test@example.com"], "subject": "Test"})
        
        assert audit_file.exists()
        lines = audit_file.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["account"] == "personal"
        assert entry["operation"] == "send"
        assert "timestamp" in entry

    def test_audit_never_logs_tokens(self, core, tmp_path):
        audit_file = tmp_path / "audit.jsonl"
        core._audit_path = audit_file
        # The audit method sanitizes sensitive fields - they should be [REDACTED]
        core._audit("personal", "send", {"access_token": "secret123", "to": ["test@example.com"]})
        
        lines = audit_file.read_text().strip().split("\n")
        entry = json.loads(lines[0])
        # Check that access_token is redacted, not the raw value
        assert entry["details"]["access_token"] == "[REDACTED]"
        assert "secret123" not in str(entry)


class TestCoreCredentials:
    @pytest.fixture
    def temp_files(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("""[accounts.personal]
provider = "gmail"
capabilities = ["mail"]
""")
        state_file = tmp_path / "credentials.json"
        state_file.parent.mkdir(exist_ok=True)
        state_file.write_text('{"accounts": {"personal": {"refresh_token": "rt123", "client_id": "cid", "client_secret": "csecret"}}}')
        return config_file, state_file

    def test_load_credentials(self, temp_files):
        config_file, state_file = temp_files
        core = Core(config_file=config_file, state_file=state_file)
        creds = core._load_credentials("personal")
        assert creds.refresh_token == "rt123"
        assert creds.client_id == "cid"

    def test_save_credentials(self, temp_files):
        config_file, state_file = temp_files
        core = Core(config_file=config_file, state_file=state_file)
        from mailhub.core import AccountCredentials
        creds = AccountCredentials(access_token="at123", refresh_token="rt123", expires_at=9999999999, client_id="cid", client_secret="csecret")
        core._save_credentials("personal", creds)
        
        # Reload and verify
        core2 = Core(config_file=config_file, state_file=state_file)
        loaded = core2._load_credentials("personal")
        assert loaded.access_token == "at123"
        assert loaded.expires_at == 9999999999


