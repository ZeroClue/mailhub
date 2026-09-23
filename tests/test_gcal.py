"""Unit tests for mailhub.gcal module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from mailhub.calendar import Calendar, Event, EventStatus, FreeBusyPeriod, FreeBusyRequest
from mailhub.core import Core, RetryPolicy
from mailhub.gcal import GoogleCalendarAdapter


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
def gcal_adapter(mock_core):
    return GoogleCalendarAdapter(mock_core)


class TestGoogleCalendarAdapter:
    def test_calendars(self, gcal_adapter, mock_core):
        mock_response = MockResponse({
            "items": [
                {"id": "cal1", "summary": "Personal", "accessRole": "owner", "primary": True},
                {"id": "cal2", "summary": "Work", "accessRole": "writer", "primary": False},
            ]
        })
        
        with patch.object(gcal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = gcal_adapter.calendars("test_alias")
            
            assert len(result) == 2
            assert result[0].id == "cal1"
            assert result[0].name == "Personal"
            assert result[0].primary is True
            assert result[1].id == "cal2"
            assert result[1].primary is False

    def test_events(self, gcal_adapter, mock_core):
        mock_response = MockResponse({
            "items": [
                {
                    "id": "evt1",
                    "summary": "Meeting",
                    "start": {"dateTime": "2024-01-15T10:00:00Z"},
                    "end": {"dateTime": "2024-01-15T11:00:00Z"},
                    "status": "confirmed",
                },
                {
                    "id": "evt2",
                    "summary": "Lunch",
                    "start": {"dateTime": "2024-01-15T12:00:00Z"},
                    "end": {"dateTime": "2024-01-15T13:00:00Z"},
                    "status": "tentative",
                },
            ],
            "nextPageToken": "next_token"
        })
        
        with patch.object(gcal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = gcal_adapter.events("test_alias", "cal1")
            
            assert len(result["events"]) == 2
            assert result["events"][0].id == "evt1"
            assert result["events"][0].summary == "Meeting"
            assert result["next_page_token"] == "next_token"

    def test_get_event(self, gcal_adapter, mock_core):
        mock_response = MockResponse({
            "id": "evt1",
            "summary": "Meeting",
            "start": {"dateTime": "2024-01-15T10:00:00Z"},
            "end": {"dateTime": "2024-01-15T11:00:00Z"},
            "status": "confirmed",
        })
        
        with patch.object(gcal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = gcal_adapter.get_event("test_alias", "cal1", "evt1")
            
            assert result.id == "evt1"
            assert result.summary == "Meeting"

    def test_freebusy(self, gcal_adapter, mock_core):
        mock_response = MockResponse({
            "calendars": {
                "cal1": {
                    "busy": [
                        {"start": "2024-01-15T10:00:00Z", "end": "2024-01-15T11:00:00Z"},
                    ]
                }
            }
        })
        
        with patch.object(gcal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            request = FreeBusyRequest(
                calendar_ids=["cal1"],
                time_min=datetime(2024, 1, 1),
                time_max=datetime(2024, 1, 31),
            )
            result = gcal_adapter.freebusy("test_alias", request)
            
            assert "cal1" in result.calendars
            assert len(result.calendars["cal1"]) == 1

    def test_create_event_requires_confirm_with_attendees(self, gcal_adapter, mock_core):
        from mailhub.calendar import Attendee
        event = Event(
            id="",
            calendar_id="cal1",
            summary="Meeting",
            attendees=(Attendee(email="test@example.com"),),
        )
        
        with pytest.raises(ValueError, match="confirm=True"):
            gcal_adapter.create_event("test_alias", "cal1", event, confirm=False)

    def test_create_event_no_attendees_no_confirm(self, gcal_adapter, mock_core):
        mock_response = MockResponse({
            "id": "new_evt",
            "summary": "Meeting",
            "start": {"dateTime": "2024-01-15T10:00:00Z"},
            "end": {"dateTime": "2024-01-15T11:00:00Z"},
            "status": "confirmed",
        })
        
        with patch.object(gcal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            event = Event(
                id="",
                calendar_id="cal1",
                summary="Meeting",
            )
            result = gcal_adapter.create_event("test_alias", "cal1", event, confirm=False)
            
            assert result.id == "new_evt"

    def test_update_event(self, gcal_adapter, mock_core):
        mock_response = MockResponse({
            "id": "evt1",
            "summary": "Updated Meeting",
            "start": {"dateTime": "2024-01-15T10:00:00Z"},
            "end": {"dateTime": "2024-01-15T11:00:00Z"},
            "status": "confirmed",
        })
        
        with patch.object(gcal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            event = Event(
                id="evt1",
                calendar_id="cal1",
                summary="Updated Meeting",
            )
            result = gcal_adapter.update_event("test_alias", "cal1", "evt1", event, confirm=True)
            
            assert result.id == "evt1"
            assert result.summary == "Updated Meeting"

    def test_delete_event(self, gcal_adapter, mock_core):
        mock_get = MockResponse({
            "id": "evt1",
            "summary": "Meeting",
            "attendees": [],
        })
        mock_delete = MockResponse({}, status_code=204)
        
        with patch.object(gcal_adapter, '_request') as mock_request:
            mock_request.side_effect = [mock_get, mock_delete]
            gcal_adapter.delete_event("test_alias", "cal1", "evt1", confirm=True)
            
            assert mock_request.call_count == 2

    def test_delete_event_requires_confirm_with_attendees(self, gcal_adapter, mock_core):
        mock_get = MockResponse({
            "id": "evt1",
            "attendees": [{"email": "test@example.com"}],
        })
        
        with patch.object(gcal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_get
            with pytest.raises(ValueError, match="confirm=True"):
                gcal_adapter.delete_event("test_alias", "cal1", "evt1", confirm=False)

    def test_retry_on_429(self, gcal_adapter, mock_core):
        call_count = [0]
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=429, headers={"Retry-After": "0"})
            return MockResponse({
                "id": "evt1", "summary": "Test",
                "start": {"dateTime": "2024-01-15T10:00:00Z"},
                "end": {"dateTime": "2024-01-15T11:00:00Z"},
                "status": "confirmed",
            })
        
        mock_client.request = mock_request
        gcal_adapter._client = mock_client
        
        result = gcal_adapter.get_event("test_alias", "cal1", "evt1")
        
        assert result.id == "evt1"
        assert call_count[0] == 2

    def test_401_refreshes_token(self, gcal_adapter, mock_core):
        call_count = [0]
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=401)
            return MockResponse({
                "id": "evt1", "summary": "Test",
                "start": {"dateTime": "2024-01-15T10:00:00Z"},
                "end": {"dateTime": "2024-01-15T11:00:00Z"},
                "status": "confirmed",
            })
        
        mock_client.request = mock_request
        gcal_adapter._client = mock_client
        
        result = gcal_adapter.get_event("test_alias", "cal1", "evt1")
        
        assert result.id == "evt1"
        assert call_count[0] == 2
        mock_core._refresh_access_token.assert_called_once_with("test_alias")


