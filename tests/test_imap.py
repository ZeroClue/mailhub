"""Tests for IMAP adapter with mocked IMAP connections."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mailhub.imap import IMAPAdapter, IMAPConfig
from mailhub.core import CoreError, AccountCredentials


class MockCore:
    """Mock core for testing IMAPAdapter."""
    
    def __init__(self):
        self._config = MockConfig()
        self._credentials = {
            "test_account": AccountCredentials(
                client_id="user@example.com",
                client_secret="password123",
                refresh_token="password123",
            )
        }
        self._configs = {}
    
    def _load_credentials(self, alias):
        return self._credentials[alias]


class MockConfig:
    """Mock config with accounts."""
    
    def __init__(self):
        self._accounts = {
            "test_account": MagicMock(
                alias="test_account",
                provider="imap",
                email="user@example.com",
                imap_host="imap.example.com",
                imap_port=993,
                imap_use_ssl=True,
                imap_use_starttls=False,
                smtp_host="smtp.example.com",
                smtp_port=587,
                smtp_use_ssl=False,
                smtp_use_starttls=True,
                auth_method="plain",
            )
        }
        self._raw = {
            "accounts": {
                "test_account": {
                    "imap_host": "imap.example.com",
                    "imap_port": 993,
                    "imap_use_ssl": True,
                }
            },
            "imap": {}
        }
    
    def account(self, alias):
        if alias in self._accounts:
            return self._accounts[alias]
        raise CoreError(f"Unknown account: {alias}")


@pytest.fixture
def mock_core():
    return MockCore()


@pytest.fixture
def mock_imap():
    """Mock IMAP connection factory."""
    with patch("mailhub.imap.imaplib.IMAP4_SSL") as mock_ssl:
        mock_conn = MagicMock()
        mock_ssl.return_value = mock_conn
        
        # Default successful responses
        mock_conn.login.return_value = ("OK", [b"Logged in"])
        mock_conn.select.return_value = ("OK", [b"10"])
        mock_conn.list.return_value = ("OK", [
            b'(\\HasNoChildren) "." "INBOX"',
            b'(\\HasNoChildren) "." "Sent"',
            b'(\\HasNoChildren) "." "Drafts"',
            b'(\\HasChildren) "." "Archive"',
            b'(\\HasNoChildren) "." "Archive.Subfolder"',
        ])
        mock_conn.search.return_value = ("OK", [b"1 2 3"])
        mock_conn.fetch.return_value = ("OK", [(b"1", b"Message-ID: <test@example.com>\r\nFrom: test@example.com\r\nSubject: Test\r\n\r\nBody")])
        mock_conn.copy.return_value = ("OK", [b"Done"])
        mock_conn.store.return_value = ("OK", [b"Done"])
        mock_conn.expunge.return_value = ("OK", [b"1"])
        mock_conn.logout.return_value = ("OK", [b"Bye"])
        mock_conn.xlist.return_value = ("NO", [b"Xlist not supported"])
        mock_conn.status.return_value = ("OK", [b'INBOX (MESSAGES 10 UNSEEN 2 UIDNEXT 15 UIDVALIDITY 123)'])
        
        yield mock_conn


@pytest.fixture
def adapter(mock_core, mock_imap):
    return IMAPAdapter(mock_core)


def test_folders_parses_imap_list_response(adapter, mock_imap):
    """Test that folders() correctly parses IMAP LIST response with quoted and unquoted names."""
    folders = adapter.folders("test_account")
    
    assert len(folders) == 5
    folder_names = [f["name"] for f in folders]
    assert "INBOX" in folder_names
    assert "Sent" in folder_names
    assert "Drafts" in folder_names
    assert "Archive" in folder_names
    assert "Archive.Subfolder" in folder_names
    for f in folders:
        assert f["id"] == f["name"]


def test_folders_handles_empty_response(adapter, mock_imap):
    """Test folders() handles empty LIST response."""
    mock_imap.list.return_value = ("OK", [])
    
    folders = adapter.folders("test_account")
    
    assert folders == []


def test_folders_raises_on_imap_error(adapter, mock_imap):
    """Test folders() raises CoreError on IMAP error."""
    from mailhub.core import CoreError
    mock_imap.list.return_value = ("NO", [b"Error"])
    
    with pytest.raises(CoreError, match="Failed to list folders"):
        adapter.folders("test_account")


def test_search_returns_messages(adapter, mock_imap):
    """Test search() returns parsed messages."""
    result = adapter.search("test_account", "from:test", max_results=10)
    
    assert "messages" in result
    assert len(result["messages"]) > 0
    msg = result["messages"][0]
    assert "id" in msg
    assert "headers" in msg
    assert "text_body" in msg


def test_search_handles_no_results(adapter, mock_imap):
    """Test search() returns empty list when no messages found."""
    mock_imap.search.return_value = ("OK", [b""])
    
    result = adapter.search("test_account", "nonexistent", max_results=10)
    
    assert result["messages"] == []


def test_get_finds_message_across_folders(adapter, mock_imap):
    """Test get() searches across multiple folders to find message."""
    mock_imap.search.return_value = ("OK", [b"1"])
    
    result = adapter.get("test_account", "<test@example.com>")
    
    assert result["id"] == "test@example.com"
    assert "headers" in result


def test_get_raises_when_not_found(adapter, mock_imap):
    """Test get() raises CoreError when message not found in any folder."""
    from mailhub.core import CoreError
    mock_imap.search.return_value = ("OK", [b""])
    
    with pytest.raises(CoreError, match="Message not found"):
        adapter.get("test_account", "<notfound@example.com>")


def test_set_message_flags_add_and_remove(adapter, mock_imap):
    """Test set_message_flags() adds and removes flags."""
    mock_imap.search.return_value = ("OK", [b"1", b"2"])
    mock_imap.store.return_value = ("OK", [b"Done"])
    
    result = adapter.set_message_flags(
        "test_account",
        ["<msg1>", "<msg2>"],
        add_flags=["\\Seen"],
        remove_flags=["\\Flagged"]
    )
    
    assert result["results"][0]["status"] == "updated"
    assert result["results"][1]["status"] == "updated"


def test_move_message_copies_and_deletes(adapter, mock_imap):
    """Test move() copies message to destination and marks deleted in source."""
    mock_imap.search.return_value = ("OK", [b"1"])
    mock_imap.copy.return_value = ("OK", [b"Done"])
    mock_imap.store.return_value = ("OK", [b"Done"])
    mock_imap.expunge.return_value = ("OK", [b"1"])
    
    result = adapter.move("test_account", "<msg1>", "Archive")
    
    assert result["status"] == "moved"
    assert result["id"] == "<msg1>"


def test_imap_config_parses_correctly():
    """Test IMAPConfig dataclass parses settings correctly."""
    config = IMAPConfig(
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="password",
        use_ssl=True,
        smtp_host="smtp.example.com",
    )
    
    assert config.get_smtp_host() == "smtp.example.com"
    assert config.get_smtp_port() == 465
    assert config.get_smtp_username() == "user@example.com"
    assert config.get_smtp_password() == "password"


def test_imap_config_fallback_to_imap_settings():
    """Test SMTP settings fall back to IMAP settings when not provided."""
    config = IMAPConfig(
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="password",
        use_ssl=True,
    )
    
    assert config.get_smtp_host() == "smtp.example.com"
    assert config.get_smtp_port() == 465
    assert config.get_smtp_username() == "user@example.com"
    assert config.get_smtp_password() == "password"


def test_imap_config_smtp_ssl_port():
    """Test SMTP port 465 when SSL is enabled."""
    config = IMAPConfig(
        host="imap.example.com",
        port=993,
        username="user@example.com",
        password="password",
        use_ssl=True,
        smtp_use_ssl=True,
    )
    
    assert config.get_smtp_port() == 465


def test_folder_status_parses_imap_status(adapter, mock_imap):
    """Test folder_status() parses IMAP STATUS response."""
    mock_imap.status.return_value = ("OK", [b'INBOX (MESSAGES 10 UNSEEN 2 UIDNEXT 15 UIDVALIDITY 123)'])
    
    result = adapter.folder_status("test_account", "INBOX")
    
    assert result["folder"] == "INBOX"
    assert result["messages"] == 10
    assert result["unseen"] == 2
    assert result["uidnext"] == 15
    assert result["uidvalidity"] == 123


def test_folder_statuses_calls_status_for_each_folder(adapter, mock_imap):
    """Test folder_statuses() calls folder_status for each folder."""
    with patch.object(adapter, "folders", return_value=[
        {"name": "INBOX", "id": "INBOX"},
        {"name": "Sent", "id": "Sent"},
    ]):
        with patch.object(adapter, "folder_status") as mock_status:
            mock_status.side_effect = [
                {"folder": "INBOX", "messages": 10, "unseen": 2},
                {"folder": "Sent", "messages": 5, "unseen": 0},
            ]
            result = adapter.folder_statuses("test_account")
    
    assert len(result) == 2
    assert mock_status.call_count == 2


def test_special_use_folders_detects_xlist(adapter, mock_imap):
    """Test get_special_use_folders() uses XLIST when available."""
    mock_imap.xlist.return_value = ("OK", [
        b'(\\HasNoChildren \\Inbox) "." "INBOX"',
        b'(\\HasNoChildren \\Sent) "." "[Gmail]/Sent Mail"',
        b'(\\HasNoChildren \\Drafts) "." "[Gmail]/Drafts"',
        b'(\\HasNoChildren \\Trash) "." "[Gmail]/Trash"',
        b'(\\HasNoChildren \\Junk) "." "[Gmail]/Spam"',
    ])
    
    result = adapter.get_special_use_folders("test_account")
    
    assert result["inbox"] == "INBOX"
    assert result["sent"] == "[Gmail]/Sent Mail"
    assert result["drafts"] == "[Gmail]/Drafts"
    assert result["trash"] == "[Gmail]/Trash"
    assert result["junk"] == "[Gmail]/Spam"


def test_special_use_folders_fallback_to_common_names(adapter, mock_imap):
    """Test get_special_use_folders() falls back to common names when XLIST fails."""
    from unittest.mock import patch
    with patch.object(adapter, "folders", return_value=[
        {"name": "INBOX", "id": "INBOX"},
        {"name": "Sent Items", "id": "Sent Items"},
        {"name": "Deleted Items", "id": "Deleted Items"},
        {"name": "Junk E-mail", "id": "Junk E-mail"},
    ]):
        result = adapter.get_special_use_folders("test_account")
    
    assert result["inbox"] == "INBOX"
    assert result["sent"] == "Sent Items"
    assert result["trash"] == "Deleted Items"
    assert result["junk"] == "Junk E-mail"


