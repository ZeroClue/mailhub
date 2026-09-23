"""Unit tests for mailhub.graph module."""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from mailhub.core import Core, RetryPolicy
from mailhub.graph import GraphAdapter


class MockResponse:
    def __init__(self, json_data, status_code=200, headers=None):
        self._json_data = json_data
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=MagicMock(), response=self)


@pytest.fixture
def mock_core():
    core = MagicMock(spec=Core)
    core._retry_policy = RetryPolicy()
    core._ensure_access_token = MagicMock(return_value="test_access_token")
    core._refresh_access_token = MagicMock(return_value="new_access_token")
    return core


@pytest.fixture
def graph_adapter(mock_core):
    return GraphAdapter(mock_core)


class TestGraphAdapter:
    def test_profile(self, graph_adapter, mock_core):
        mock_response = MockResponse({
            "mail": "test@outlook.com",
            "userPrincipalName": "test@outlook.com",
            "displayName": "Test User",
            "id": "user123"
        })
        
        with patch.object(graph_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_adapter.profile("test_alias")
            
            assert result["email"] == "test@outlook.com"
            assert result["provider"] == "graph"

    def test_folders(self, graph_adapter, mock_core):
        mock_response = MockResponse({
            "value": [
                {"id": "inbox", "displayName": "Inbox", "childFolderCount": 0, "totalItemCount": 50, "unreadItemCount": 5},
                {"id": "sent", "displayName": "Sent Items", "childFolderCount": 0, "totalItemCount": 30, "unreadItemCount": 0},
                {"id": "deleted", "displayName": "Deleted Items", "childFolderCount": 0, "totalItemCount": 10, "unreadItemCount": 0},
            ]
        })
        
        with patch.object(graph_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_adapter.folders("test_alias")
            
            assert len(result) == 3
            assert result[0]["name"] == "Inbox"

    def test_search(self, graph_adapter, mock_core):
        mock_response = MockResponse({
            "value": [
                {"id": "msg1", "subject": "Test 1", "from": {"emailAddress": {"address": "a@b.com"}}, "toRecipients": [], "ccRecipients": [], "body": {"contentType": "text", "content": "Body 1"}, "receivedDateTime": "2024-01-01T00:00:00Z", "hasAttachments": False, "isRead": False},
                {"id": "msg2", "subject": "Test 2", "from": {"emailAddress": {"address": "c@d.com"}}, "toRecipients": [], "ccRecipients": [], "body": {"contentType": "html", "content": "<p>Body 2</p>"}, "receivedDateTime": "2024-01-02T00:00:00Z", "hasAttachments": True, "isRead": True},
            ],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/messages?$skiptoken=abc123"
        })
        
        with patch.object(graph_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_adapter.search("test_alias", "test query", max_results=10)
            
            assert len(result["messages"]) == 2
            assert result["next_page_token"] == "abc123"

    def test_get_message(self, graph_adapter, mock_core):
        mock_response = MockResponse({
            "id": "msg1",
            "conversationId": "conv1",
            "subject": "Test Subject",
            "from": {"emailAddress": {"name": "Sender", "address": "sender@example.com"}},
            "toRecipients": [{"emailAddress": {"name": "Recipient", "address": "recipient@example.com"}}],
            "ccRecipients": [],
            "body": {"contentType": "text", "content": "Hello World"},
            "receivedDateTime": "2024-01-01T00:00:00Z",
            "hasAttachments": False,
            "isRead": False,
        })
        
        with patch.object(graph_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_adapter.get("test_alias", "msg1")
            
            assert result["id"] == "msg1"
            assert result["subject"] == "Test Subject"

    def test_send(self, graph_adapter, mock_core):
        mock_profile = MockResponse({"mail": "test@outlook.com"})
        mock_send = MockResponse({}, status_code=202)
        
        with patch.object(graph_adapter, '_request') as mock_request:
            mock_request.side_effect = [mock_profile, mock_send]
            result = graph_adapter.send(
                "test_alias",
                to=["recipient@example.com"],
                subject="Test",
                text_body="Hello",
            )
            
            assert result["status"] == "sent"

    def test_draft(self, graph_adapter, mock_core):
        mock_profile = MockResponse({"mail": "test@outlook.com"})
        mock_draft = MockResponse({"id": "draft123"})
        
        with patch.object(graph_adapter, '_request') as mock_request:
            mock_request.side_effect = [mock_profile, mock_draft]
            result = graph_adapter.draft(
                "test_alias",
                to=["recipient@example.com"],
                subject="Test Draft",
                text_body="Draft body",
            )
            
            assert result["id"] == "draft123"

    def test_move_returns_new_id(self, graph_adapter, mock_core):
        """Graph move returns a new message ID."""
        mock_folders = MockResponse({
            "value": [{"id": "inbox", "displayName": "Inbox"}, {"id": "archive", "displayName": "Archive"}]
        })
        mock_move = MockResponse({"id": "new_msg_id", "subject": "Test"})
        
        with patch.object(graph_adapter, '_request') as mock_request:
            mock_request.side_effect = [mock_folders, mock_move]
            result = graph_adapter.move("test_alias", "old_msg_id", "Archive")
            
            assert result["id"] == "new_msg_id"
            assert result["folder"] == "Archive"

    def test_trash(self, graph_adapter, mock_core):
        mock_folders = MockResponse({
            "value": [{"id": "deleted", "displayName": "Deleted Items"}]
        })
        mock_move = MockResponse({"id": "new_msg_id"})
        
        with patch.object(graph_adapter, '_request') as mock_request:
            mock_request.side_effect = [mock_folders, mock_move]
            result = graph_adapter.trash("test_alias", "msg1")
            
            assert result["id"] == "new_msg_id"

    def test_retry_on_429(self, graph_adapter, mock_core):
        """Test retry logic on 429 status by patching the internal client."""
        call_count = [0]
        
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=429, headers={"Retry-After": "0"})
            return MockResponse({"id": "msg1", "subject": "Test"})
        
        mock_client.request = mock_request
        graph_adapter._client = mock_client
        
        result = graph_adapter.get("test_alias", "msg1")
        
        assert result["id"] == "msg1"
        assert call_count[0] == 2

    def test_401_refreshes_token(self, graph_adapter, mock_core):
        """Test token refresh on 401 by patching the internal client."""
        call_count = [0]
        
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=401)
            return MockResponse({"id": "msg1", "subject": "Test"})
        
        mock_client.request = mock_request
        graph_adapter._client = mock_client
        
        result = graph_adapter.get("test_alias", "msg1")
        
        assert result["id"] == "msg1"
        assert call_count[0] == 2
        mock_core._refresh_access_token.assert_called_once_with("test_alias")


