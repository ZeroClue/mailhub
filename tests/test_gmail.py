"""Unit tests for mailhub.gmail module."""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from mailhub.core import Core, RetryPolicy
from mailhub.gmail import GmailAdapter


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
def gmail_adapter(mock_core):
    return GmailAdapter(mock_core)


class TestGmailAdapter:
    def test_profile(self, gmail_adapter, mock_core):
        mock_response = MockResponse({
            "emailAddress": "test@gmail.com",
            "messagesTotal": 100,
            "threadsTotal": 50,
            "historyId": "12345"
        })
        
        with patch.object(gmail_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = gmail_adapter.profile("test_alias")
            
            assert result["email"] == "test@gmail.com"
            assert result["provider"] == "gmail"
            assert result["messages_total"] == 100

    def test_folders(self, gmail_adapter, mock_core):
        mock_response = MockResponse({
            "labels": [
                {"id": "INBOX", "name": "INBOX", "type": "system", "messagesTotal": 50},
                {"id": "SENT", "name": "SENT", "type": "system", "messagesTotal": 30},
            ]
        })
        
        with patch.object(gmail_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = gmail_adapter.folders("test_alias")
            
            assert len(result) == 2
            assert result[0]["id"] == "INBOX"
            assert result[0]["name"] == "INBOX"

    def test_search(self, gmail_adapter, mock_core):
        # Mock list messages response
        list_response = MockResponse({
            "messages": [{"id": "msg1"}, {"id": "msg2"}],
            "nextPageToken": "next_page_token",
            "resultSizeEstimate": 2
        })
        
        # Mock get message response
        get_response = MockResponse({
            "id": "msg1",
            "threadId": "thread1",
            "labelIds": ["INBOX"],
            "snippet": "Test snippet",
            "payload": {
                "headers": [
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"},
                ],
                "body": {"data": "", "size": 0},
                "parts": []
            }
        })
        
        with patch.object(gmail_adapter, '_request') as mock_request:
            mock_request.side_effect = [list_response, get_response, get_response]
            result = gmail_adapter.search("test_alias", "from:test", max_results=10)
            
            assert "messages" in result
            assert len(result["messages"]) == 2
            assert result["next_page_token"] == "next_page_token"

    def test_get_message(self, gmail_adapter, mock_core):
        mock_response = MockResponse({
            "id": "msg1",
            "threadId": "thread1",
            "labelIds": ["INBOX"],
            "snippet": "Test snippet",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Sender <sender@example.com>"},
                    {"name": "To", "value": "Recipient <recipient@example.com>"},
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"},
                ],
                "body": {"data": "", "size": 0},
                "parts": []
            }
        })
        
        with patch.object(gmail_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = gmail_adapter.get("test_alias", "msg1")
            
            assert result["id"] == "msg1"
            assert result["subject"] == "Test Subject"
            assert result["from"]["addr"] == "Sender <sender@example.com>"

    def test_send(self, gmail_adapter, mock_core):
        mock_profile = MockResponse({
            "emailAddress": "test@gmail.com"
        })
        mock_send = MockResponse({"id": "sent_msg_id", "threadId": "thread1"})
        
        with patch.object(gmail_adapter, '_request') as mock_request:
            mock_request.side_effect = [mock_profile, mock_send]
            result = gmail_adapter.send(
                "test_alias",
                to=["recipient@example.com"],
                subject="Test",
                text_body="Hello",
            )
            
            assert result["id"] == "sent_msg_id"

    def test_draft(self, gmail_adapter, mock_core):
        mock_profile = MockResponse({"emailAddress": "test@gmail.com"})
        mock_draft = MockResponse({"id": "draft123"})
        
        with patch.object(gmail_adapter, '_request') as mock_request:
            mock_request.side_effect = [mock_profile, mock_draft]
            result = gmail_adapter.draft(
                "test_alias",
                to=["recipient@example.com"],
                subject="Test Draft",
                text_body="Draft body",
            )
            
            assert result["id"] == "draft123"

    def test_move_to_inbox(self, gmail_adapter, mock_core):
        mock_get = MockResponse({
            "id": "msg1",
            "labelIds": ["INBOX", "UNREAD"],
            "payload": {"headers": [], "parts": []}
        })
        mock_modify = MockResponse({"id": "msg1", "labelIds": ["INBOX"]})
        
        with patch.object(gmail_adapter, '_request') as mock_request:
            mock_request.side_effect = [mock_get, mock_modify]
            result = gmail_adapter.move("test_alias", "msg1", "inbox")
            
            assert result["id"] == "msg1"

    def test_move_to_archive(self, gmail_adapter, mock_core):
        mock_get = MockResponse({
            "id": "msg1",
            "labelIds": ["INBOX"],
            "payload": {"headers": [], "parts": []}
        })
        mock_modify = MockResponse({"id": "msg1", "labelIds": []})
        
        with patch.object(gmail_adapter, '_request') as mock_request:
            mock_request.side_effect = [mock_get, mock_modify]
            result = gmail_adapter.move("test_alias", "msg1", "archive")
            
            assert result["id"] == "msg1"

    def test_trash(self, gmail_adapter, mock_core):
        mock_get = MockResponse({
            "id": "msg1",
            "labelIds": ["INBOX"],
            "payload": {"headers": [], "parts": []}
        })
        mock_modify = MockResponse({"id": "msg1", "labelIds": ["TRASH"]})
        
        with patch.object(gmail_adapter, '_request') as mock_request:
            mock_request.side_effect = [mock_get, mock_modify]
            result = gmail_adapter.trash("test_alias", "msg1")
            
            assert result["id"] == "msg1"

    def test_retry_on_429(self, gmail_adapter, mock_core):
        """Test retry logic on 429 status by patching the internal client."""
        call_count = [0]
        
        # Create a mock client that returns 429 once then success
        original_client = gmail_adapter._get_client()
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Return 429 response
                response = MockResponse({}, status_code=429, headers={"Retry-After": "0"})
                return response
            # Return success on second call
            return MockResponse({
                "id": "msg1", 
                "labelIds": ["INBOX"], 
                "payload": {"headers": [], "parts": []}
            })
        
        mock_client.request = mock_request
        gmail_adapter._client = mock_client
        
        result = gmail_adapter.get("test_alias", "msg1")
        
        assert result["id"] == "msg1"
        assert call_count[0] == 2

    def test_401_refreshes_token(self, gmail_adapter, mock_core):
        """Test token refresh on 401 by patching the internal client."""
        call_count = [0]
        
        original_client = gmail_adapter._get_client()
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=401)
            return MockResponse({
                "id": "msg1", 
                "labelIds": ["INBOX"], 
                "payload": {"headers": [], "parts": []}
            })
        
        mock_client.request = mock_request
        gmail_adapter._client = mock_client
        
        result = gmail_adapter.get("test_alias", "msg1")
        
        assert result["id"] == "msg1"
        assert call_count[0] == 2
        mock_core._refresh_access_token.assert_called_once_with("test_alias")

    def test_get_attachment(self, gmail_adapter, mock_core):
        mock_response = MockResponse({"data": base64.b64encode(b"attachment content").decode()})
        
        with patch.object(gmail_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = gmail_adapter.get_attachment("test_alias", "msg1", "att123")
            
            assert result == b"attachment content"


