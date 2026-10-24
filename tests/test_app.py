"""Tests for FastAPI REST API endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from mailhub.app import create_app, verify_token
from mailhub.core import Core, CoreError


@pytest.fixture
def mock_core():
    """Create a mock Core with all necessary methods."""
    core = MagicMock(spec=Core)
    
    # Mock config
    mock_account = MagicMock()
    mock_account.alias = "test_account"
    mock_account.provider = "imap"
    mock_account.capabilities = frozenset(["mail"])
    mock_account.email = "test@example.com"
    
    mock_config = MagicMock()
    mock_config.accounts = [mock_account]
    mock_config.send_policy = MagicMock()
    mock_config.send_policy.allow_anywhere = True
    mock_config.send_policy.allowlist = ()
    
    core.config = mock_config
    core.accounts = [mock_account]
    
    # Mock methods
    core.folders = MagicMock(return_value=[
        {"name": "INBOX", "id": "INBOX"},
        {"name": "Sent", "id": "Sent"},
    ])
    core.folder_status = MagicMock(return_value={
        "folder": "INBOX", "messages": 10, "unseen": 2
    })
    core.folder_statuses = MagicMock(return_value=[
        {"folder": "INBOX", "messages": 10, "unseen": 2},
        {"folder": "Sent", "messages": 5, "unseen": 0},
    ])
    core.special_use_folders = MagicMock(return_value={
        "inbox": "INBOX", "sent": "Sent", "drafts": "Drafts",
        "trash": "Trash", "junk": "Junk", "archive": "Archive"
    })
    core.create_folder = MagicMock(return_value={"name": "TestFolder", "status": "created"})
    core.delete_folder = MagicMock(return_value={"name": "TestFolder", "status": "deleted"})
    core.rename_folder = MagicMock(return_value={"old_name": "Old", "new_name": "New", "status": "renamed"})
    core.search = MagicMock(return_value={
        "messages": [{
            "id": "msg1",
            "thread_id": None,
            "headers": {"subject": "Test", "from": "test@example.com", "to": "user@example.com", "date": "2024-01-01"},
            "text_body": "Test body",
            "html_body": "",
            "attachments": [],
            "labels": [],
            "flags": [],
        }],
        "next_page_token": None
    })
    core.get = MagicMock(return_value={
        "id": "msg1",
        "thread_id": None,
        "headers": {"subject": "Test", "from": "test@example.com", "to": "user@example.com", "date": "2024-01-01"},
        "text_body": "Test body",
        "html_body": "",
        "attachments": [],
        "labels": [],
        "flags": [],
    })
    def mock_send(account, to, subject, cc=None, bcc=None, text_body=None, html_body=None,
                        in_reply_to=None, references=None, confirm=False, attachments=None):
        if not confirm:
            from mailhub.core import SendDenied
            raise SendDenied("send requires confirm=true")
        return {"id": "sent", "status": "sent"}
    
    core.send = MagicMock(side_effect=mock_send)
    core.draft = MagicMock(return_value={"id": "draft", "status": "draft"})
    core.move = MagicMock(return_value={"id": "msg1", "status": "moved"})
    core.trash = MagicMock(return_value={"id": "msg1", "status": "moved"})
    core.folder_status = MagicMock(return_value={"folder": "INBOX", "messages": 10, "unseen": 2})
    core.folder_statuses = MagicMock(return_value=[
        {"folder": "INBOX", "messages": 10, "unseen": 2},
        {"folder": "Sent", "messages": 5, "unseen": 0},
    ])
    core.special_use_folders = MagicMock(return_value={
        "inbox": "INBOX", "sent": "Sent", "drafts": "Drafts",
        "trash": "Trash", "junk": "Junk", "archive": "Archive"
    })
    core.create_folder = MagicMock(return_value={"name": "TestFolder", "status": "created"})
    core.delete_folder = MagicMock(return_value={"name": "TestFolder", "status": "deleted"})
    core.rename_folder = MagicMock(return_value={"old_name": "Old", "new_name": "New", "status": "renamed"})
    core.set_message_flags = MagicMock(return_value={"results": [{"message_id": "msg1", "status": "updated"}]})
    core.mark_read = MagicMock(return_value={"results": [{"message_id": "msg1", "status": "updated"}]})
    core.mark_unread = MagicMock(return_value={"results": [{"message_id": "msg1", "status": "updated"}]})
    core.flag_messages = MagicMock(return_value={"results": [{"message_id": "msg1", "status": "updated"}]})
    core.unflag_messages = MagicMock(return_value={"results": [{"message_id": "msg1", "status": "updated"}]})
    core.batch_move = MagicMock(return_value={"results": [{"message_id": "msg1", "status": "moved"}]})
    core.batch_delete = MagicMock(return_value={"results": [{"message_id": "msg1", "status": "deleted"}]})
    
    # Mock adapters for health check
    core._adapters = {}
    
    return core


@pytest.fixture
def app(mock_core, mock_state_path):
    """Create FastAPI app with mocked core."""
    # Set the global core BEFORE creating the app (lifespan runs at startup)
    import mailhub.app
    mailhub.app._core = mock_core
    app = create_app()
    return app


@pytest.fixture
def client(app, mock_state_path):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Auth headers for testing."""
    return {"Authorization": "Bearer test_token"}


# ============================================================================
# Fixtures for Token Verification
# ============================================================================

@pytest.fixture
def mock_state_path(tmp_path):
    """Create a temporary state file and patch state_path to use it."""
    state_file = tmp_path / "credentials.json"
    import json
    data = {
        "auth": {
            "full_token": "full_test",
            "ro_token": "ro_test",
            "test_key": "test_key"
        }
    }
    state_file.write_text(json.dumps(data))
    print(f"DEBUG: mock_state_path fixture called, state_file={state_file}")
    with patch("mailhub.store.state_path", return_value=state_file) as mock_path:
        print(f"DEBUG: patch applied, mock_path={mock_path}")
        yield state_file


@pytest.fixture
def mock_store():
    """Mock CredentialStore for token verification."""
    with patch("mailhub.store.CredentialStore") as mock_store:
        mock_store.return_value.load.return_value = {
            "auth": {
                "full_token": "full_test",
                "ro_token": "ro_test",
                "test_key": "test_key"
            }
        }
        yield mock_store


@pytest.fixture
def mock_store_x_api_key():
    """Mock CredentialStore for X-API-Key tests."""
    with patch("mailhub.store.CredentialStore") as mock_store:
        mock_store.return_value.load.return_value = {
            "auth": {
                "full_token": "test_key",
                "ro_token": "ro_key"
            }
        }
        yield mock_store


# ============================================================================
# Token Verification Tests
# ============================================================================

def test_verify_token_missing():
    """Test verify_token raises 401 when no token provided."""
    from fastapi import HTTPException
    
    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(verify_token(None, None))
    assert exc.value.status_code == 401


def test_verify_token_full():
    """Test verify_token returns 'full' for full token."""
    
    with patch("mailhub.store.CredentialStore") as mock_store:
        mock_store.return_value.load.return_value = {
            "auth": {"full_token": "full_valid", "ro_token": "ro_valid"}
        }
        
        import asyncio
        result = asyncio.run(verify_token("Bearer full_valid", None))
        assert result == "full"


def test_verify_token_ro():
    """Test verify_token returns 'ro' for read-only token."""
    
    with patch("mailhub.store.CredentialStore") as mock_store:
        mock_store.return_value.load.return_value = {
            "auth": {"full_token": "full_valid", "ro_token": "ro_valid"}
        }
        
        import asyncio
        result = asyncio.run(verify_token("Bearer ro_valid", None))
        assert result == "ro"


# ============================================================================
# Health Endpoint Tests
# ============================================================================

def test_health_endpoint(client):
    """Test /health endpoint returns basic status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_detailed_no_core(client):
    """Test /health/detailed when core not initialized."""
    with patch("mailhub.app.get_core", return_value=None):
        response = client.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert "error" in data


def test_health_detailed_with_core(client, mock_core):
    """Test /health/detailed with core initialized."""
    response = client.get("/health/detailed")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "adapters" in data


# ============================================================================
# Account Listing Tests
# ============================================================================

def test_list_accounts_success(client, mock_core, mock_state_path):
    """Test GET /accounts returns account list."""
    response = client.get("/accounts", headers={"Authorization": "Bearer full_test"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["alias"] == "test_account"
    assert data[0]["provider"] == "imap"
    assert data[0]["email"] == "test@example.com"


def test_list_accounts_no_auth(client):
    """Test GET /accounts without auth returns 401."""
    response = client.get("/accounts")
    assert response.status_code == 401


def test_list_accounts_no_core(client):
    """Test GET /accounts when core not initialized."""
    with patch("mailhub.app.get_core", return_value=None):
        response = client.get("/accounts", headers={"Authorization": "Bearer full_test"})
        assert response.status_code == 503


def test_list_accounts_ro_token(client, mock_core):
    """Test GET /accounts with read-only token."""
    response = client.get("/accounts", headers={"Authorization": "Bearer ro_test"})
    assert response.status_code == 200


# ============================================================================
# Folder Listing Tests
# ============================================================================

def test_list_folders_success(client, mock_core):
    """Test GET /accounts/{alias}/folders returns folder list."""
    response = client.get("/accounts/test_account/folders", headers={"Authorization": "Bearer full_test"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2


def test_list_folders_not_found(client, mock_core):
    """Test GET /accounts/{alias}/folders returns 404 for unknown account."""
    mock_core.folders.side_effect = CoreError("unknown account")
    
    response = client.get("/accounts/unknown/folders", headers={"Authorization": "Bearer full_test"})
    assert response.status_code == 404


def test_list_folders_ro_token(client, mock_core):
    """Test GET /accounts/{alias}/folders with read-only token."""
    response = client.get("/accounts/test_account/folders", headers={"Authorization": "Bearer ro_test"})
    assert response.status_code == 200


# ============================================================================
# Folder Status Tests
# ============================================================================

def test_folder_status_all(client, mock_core):
    """Test GET /accounts/{alias}/folders/status returns all folder statuses."""
    response = client.get("/accounts/test_account/folders/status", headers={"Authorization": "Bearer full_test"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2


def test_folder_status_single(client, mock_core):
    """Test GET /accounts/{alias}/folders/{folder}/status returns single folder status."""
    response = client.get("/accounts/test_account/folders/INBOX/status", headers={"Authorization": "Bearer full_test"})
    assert response.status_code == 200
    data = response.json()
    assert data["folder"] == "INBOX"
    assert data["messages"] == 10
    assert data["unseen"] == 2


# ============================================================================
# Special Folders Tests
# ============================================================================

def test_special_folders(client, mock_core):
    """Test GET /accounts/{alias}/special-folders returns special-use folders."""
    response = client.get("/accounts/test_account/special-folders", headers={"Authorization": "Bearer full_test"})
    assert response.status_code == 200
    data = response.json()
    assert "inbox" in data
    assert "sent" in data
    assert "drafts" in data
    assert "trash" in data
    assert "junk" in data
    assert "archive" in data


# ============================================================================
# Folder Management Tests (require full scope)
# ============================================================================

def test_create_folder_success(client, mock_core):
    """Test POST /accounts/{alias}/folders creates folder."""
    response = client.post(
        "/accounts/test_account/folders",
        headers={"Authorization": "Bearer full_test"},
        json={"name": "TestFolder"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "TestFolder"
    assert data["status"] == "created"


def test_create_folder_ro_token_fails(client, mock_core):
    """Test POST /accounts/{alias}/folders fails with RO token."""
    response = client.post(
        "/accounts/test_account/folders",
        headers={"Authorization": "Bearer ro_test"},
        json={"name": "TestFolder"}
    )
    assert response.status_code == 403


def test_delete_folder_success(client, mock_core):
    """Test DELETE /accounts/{alias}/folders/{name} deletes folder."""
    response = client.delete(
        "/accounts/test_account/folders/TestFolder",
        headers={"Authorization": "Bearer full_test"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "TestFolder"
    assert data["status"] == "deleted"


def test_rename_folder_success(client, mock_core):
    """Test PATCH /accounts/{alias}/folders/{name} renames folder."""
    response = client.patch(
        "/accounts/test_account/folders/OldName",
        headers={"Authorization": "Bearer full_test"},
        json={"new_name": "NewName"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["old_name"] == "Old"
    assert data["new_name"] == "New"
    assert data["status"] == "renamed"


# ============================================================================
# Message Search Tests
# ============================================================================

def test_search_messages_success(client, mock_core):
    """Test GET /accounts/{alias}/search returns messages."""
    response = client.get(
        "/accounts/test_account/search?q=test&max_results=10",
        headers={"Authorization": "Bearer full_test"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "messages" in data
    assert len(data["messages"]) > 0


def test_search_messages_with_pagination(client, mock_core):
    """Test search with page_token."""
    response = client.get(
        "/accounts/test_account/search?q=test&max_results=10&page_token=abc123",
        headers={"Authorization": "Bearer full_test"}
    )
    assert response.status_code == 200


def test_search_messages_ro_token(client, mock_core):
    """Test search with read-only token."""
    response = client.get(
        "/accounts/test_account/search?q=test",
        headers={"Authorization": "Bearer ro_test"}
    )
    assert response.status_code == 200


# ============================================================================
# Message Retrieval Tests
# ============================================================================

def test_get_message_success(client, mock_core):
    """Test GET /accounts/{alias}/messages/{id} returns message."""
    response = client.get(
        "/accounts/test_account/messages/msg1",
        headers={"Authorization": "Bearer full_test"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "msg1"
    assert "headers" in data
    assert "text_body" in data


def test_get_message_not_found(client, mock_core):
    """Test GET /accounts/{alias}/messages/{id} returns 404 for missing message."""
    mock_core.get.side_effect = CoreError("Message not found")
    
    response = client.get(
        "/accounts/test_account/messages/nonexistent",
        headers={"Authorization": "Bearer full_test"}
    )
    assert response.status_code == 404


def test_get_message_ro_token(client, mock_core):
    """Test get message with read-only token."""
    response = client.get(
        "/accounts/test_account/messages/msg1",
        headers={"Authorization": "Bearer ro_test"}
    )
    assert response.status_code == 200


# ============================================================================
# Send Message Tests (require full scope)
# ============================================================================

def test_send_message_success(client, mock_core):
    """Test POST /accounts/{alias}/messages sends message."""
    response = client.post(
        "/accounts/test_account/messages",
        headers={"Authorization": "Bearer full_test"},
        json={
            "to": ["recipient@example.com"],
            "subject": "Test Subject",
            "text_body": "Test body",
            "confirm": True
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "sent"
    assert data["status"] == "sent"


def test_send_message_missing_confirm(client, mock_core):
    """Test send fails without confirm=true."""
    response = client.post(
        "/accounts/test_account/messages",
        headers={"Authorization": "Bearer full_test"},
        json={
            "to": ["recipient@example.com"],
            "subject": "Test",
            "text_body": "Test body"
        }
    )
    assert response.status_code == 400


def test_send_message_ro_token_fails(client, mock_core):
    """Test send fails with RO token."""
    response = client.post(
        "/accounts/test_account/messages",
        headers={"Authorization": "Bearer ro_test"},
        json={"to": ["r@example.com"], "subject": "Test", "text_body": "Body", "confirm": True}
    )
    assert response.status_code == 403


def test_send_message_with_attachments(client, mock_core):
    """Test send with attachments."""
    response = client.post(
        "/accounts/test_account/messages",
        headers={"Authorization": "Bearer full_test"},
        json={
            "to": ["r@example.com"],
            "subject": "Test",
            "text_body": "Body",
            "confirm": True,
            "attachments": [{
                "path": "/tmp/file.txt",
                "filename": "file.txt",
                "content_type": "text/plain"
            }]
        }
    )
    assert response.status_code == 200


# ============================================================================
# Draft Tests (require full scope)
# ============================================================================

def test_create_draft_success(client, mock_core):
    """Test POST /accounts/{alias}/drafts creates draft."""
    response = client.post(
        "/accounts/test_account/drafts",
        headers={"Authorization": "Bearer full_test"},
        json={
            "to": ["r@example.com"],
            "subject": "Draft Subject",
            "text_body": "Draft body"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "draft"
    assert data["status"] == "draft"


def test_create_draft_ro_token_fails(client, mock_core):
    """Test draft creation fails with RO token."""
    response = client.post(
        "/accounts/test_account/drafts",
        headers={"Authorization": "Bearer ro_test"},
        json={"to": ["r@example.com"], "subject": "Test", "text_body": "Body"}
    )
    assert response.status_code == 403


# ============================================================================
# Message Move/Trash Tests (require full scope)
# ============================================================================

def test_move_message_success(client, mock_core):
    """Test POST /accounts/{alias}/messages/{id}/move moves message."""
    response = client.post(
        "/accounts/test_account/messages/msg1/move",
        headers={"Authorization": "Bearer full_test"},
        json={"destination": "Archive"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "msg1"
    assert data["status"] == "moved"


def test_trash_message_success(client, mock_core):
    """Test POST /accounts/{alias}/messages/{id}/trash moves to trash."""
    response = client.post(
        "/accounts/test_account/messages/msg1/trash",
        headers={"Authorization": "Bearer full_test"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "msg1"
    assert data["status"] == "moved"


def test_move_message_ro_token_fails(client, mock_core):
    """Test move fails with RO token."""
    response = client.post(
        "/accounts/test_account/messages/msg1/move",
        headers={"Authorization": "Bearer ro_test"},
        json={"destination": "Archive"}
    )
    assert response.status_code == 403


# ============================================================================
# Message Flags Tests (require full scope)
# ============================================================================

def test_set_message_flags(client, mock_core):
    """Test POST /accounts/{alias}/messages/flags sets flags."""
    response = client.post(
        "/accounts/test_account/messages/flags",
        headers={"Authorization": "Bearer full_test"},
        json={
            "message_ids": ["msg1", "msg2"],
            "add_flags": ["\\Seen"],
            "remove_flags": ["\\Flagged"]
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data


def test_mark_read(client, mock_core):
    """Test POST /accounts/{alias}/messages/mark-read."""
    response = client.post(
        "/accounts/test_account/messages/mark-read",
        headers={"Authorization": "Bearer full_test"},
        json={"message_ids": ["msg1"]}
    )
    assert response.status_code == 200


def test_mark_unread(client, mock_core):
    """Test POST /accounts/{alias}/messages/mark-unread."""
    response = client.post(
        "/accounts/test_account/messages/mark-unread",
        headers={"Authorization": "Bearer full_test"},
        json={"message_ids": ["msg1"]}
    )
    assert response.status_code == 200


def test_flag_messages(client, mock_core):
    """Test POST /accounts/{alias}/messages/flag."""
    response = client.post(
        "/accounts/test_account/messages/flag",
        headers={"Authorization": "Bearer full_test"},
        json={"message_ids": ["msg1"]}
    )
    assert response.status_code == 200


def test_unflag_messages(client, mock_core):
    """Test POST /accounts/{alias}/messages/unflag."""
    response = client.post(
        "/accounts/test_account/messages/unflag",
        headers={"Authorization": "Bearer full_test"},
        json={"message_ids": ["msg1"]}
    )
    assert response.status_code == 200


# ============================================================================
# Batch Operations Tests (require full scope)
# ============================================================================

def test_batch_move(client, mock_core):
    """Test POST /accounts/{alias}/messages/batch-move."""
    response = client.post(
        "/accounts/test_account/messages/batch-move",
        headers={"Authorization": "Bearer full_test"},
        json={"message_ids": ["msg1", "msg2"], "destination": "Archive"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data


def test_batch_delete(client, mock_core):
    """Test POST /accounts/{alias}/messages/batch-delete."""
    response = client.post(
        "/accounts/test_account/messages/batch-delete",
        headers={"Authorization": "Bearer full_test"},
        json={"message_ids": ["msg1", "msg2"]}
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data


# ============================================================================
# Message Flags Single Endpoints
# ============================================================================

def test_mark_read_endpoint(client, mock_core):
    """Test POST /accounts/{alias}/messages/mark-read."""
    response = client.post(
        "/accounts/test_account/messages/mark-read",
        headers={"Authorization": "Bearer full_test"},
        json={"message_ids": ["msg1"]}
    )
    assert response.status_code == 200


def test_flag_endpoint(client, mock_core):
    """Test POST /accounts/{alias}/messages/flag."""
    response = client.post(
        "/accounts/test_account/messages/flag",
        headers={"Authorization": "Bearer full_test"},
        json={"message_ids": ["msg1"]}
    )
    assert response.status_code == 200


# ============================================================================
# Health Detailed with Adapters
# ============================================================================

def test_health_detailed_adapters(client, mock_core):
    """Test health/detailed includes adapter status."""
    mock_core._adapters = {
        "imap": MagicMock(),
        "gmail": MagicMock(),
    }
    
    response = client.get("/health/detailed")
    assert response.status_code == 200
    data = response.json()
    assert "adapters" in data


# ============================================================================
# Error Handling Tests
# ============================================================================

def test_core_error_returns_400(client, mock_core):
    """Test CoreError returns 400."""
    mock_core.search.side_effect = CoreError("Invalid query")
    
    response = client.get(
        "/accounts/test_account/search?q=invalid",
        headers={"Authorization": "Bearer full_test"}
    )
    assert response.status_code == 400


def test_core_error_returns_404_for_get(client, mock_core):
    """Test CoreError on get returns 404."""
    mock_core.get.side_effect = CoreError("Message not found")
    
    response = client.get(
        "/accounts/test_account/messages/msg1",
        headers={"Authorization": "Bearer full_test"}
    )
    assert response.status_code == 404


def test_invalid_token_returns_401(client):
    """Test invalid token returns 401."""
    with patch("mailhub.store.CredentialStore") as mock_store:
        mock_store.return_value.load.return_value = {
            "auth": {"full_token": "valid", "ro_token": "ro_valid"}
        }
        response = client.get("/accounts", headers={"Authorization": "Bearer invalid_token"})
        assert response.status_code == 401


def test_missing_authorization_returns_401(client):
    """Test missing authorization returns 401."""
    response = client.get("/accounts")
    assert response.status_code == 401


# ============================================================================
# X-API-Key Header Tests
# ============================================================================

def test_x_api_key_header(client, mock_core, mock_store_x_api_key):
    """Test X-API-Key header works as alternative to Authorization."""
    response = client.get("/accounts", headers={"X-API-Key": "test_key"})
    assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
