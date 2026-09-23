"""Unit tests for mailhub.gcal_graph module."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from mailhub.calendar import Calendar, Event, FreeBusyPeriod, FreeBusyRequest
from mailhub.core import Core, RetryPolicy
from mailhub.gcal_graph import GraphCalendarAdapter


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
def graph_cal_adapter(mock_core):
    return GraphCalendarAdapter(mock_core)


class TestGraphCalendarAdapter:
    def test_calendars(self, graph_cal_adapter, mock_core):
        mock_response = MockResponse({
            "value": [
                {"id": "cal1", "name": "Personal", "isDefaultCalendar": True, "color": "auto"},
                {"id": "cal2", "name": "Work", "isDefaultCalendar": False, "color": "blue"},
            ]
        })
        
        with patch.object(graph_cal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_cal_adapter.calendars("test_alias")
            
            assert len(result) == 2
            assert result[0].id == "cal1"
            assert result[0].name == "Personal"
            assert result[0].primary is True
            assert result[1].id == "cal2"
            assert result[1].primary is False

    def test_events(self, graph_cal_adapter, mock_core):
        mock_response = MockResponse({
            "value": [
                {
                    "id": "evt1",
                    "subject": "Meeting",
                    "start": {"dateTime": "2024-01-15T10:00:00Z", "timeZone": "UTC"},
                    "end": {"dateTime": "2024-01-15T11:00:00Z", "timeZone": "UTC"},
                    "showAs": "busy",
                },
                {
                    "id": "evt2",
                    "subject": "Lunch",
                    "start": {"dateTime": "2024-01-15T12:00:00Z", "timeZone": "UTC"},
                    "end": {"dateTime": "2024-01-15T13:00:00Z", "timeZone": "UTC"},
                    "showAs": "tentative",
                },
            ],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/calendars/cal1/events?$skiptoken=abc123"
        })
        
        with patch.object(graph_cal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_cal_adapter.events("test_alias", "cal1")
            
            assert len(result["events"]) == 2
            assert result["events"][0].id == "evt1"
            assert result["next_page_token"] == "abc123"

    def test_get_event(self, graph_cal_adapter, mock_core):
        mock_response = MockResponse({
            "id": "evt1",
            "subject": "Meeting",
            "start": {"dateTime": "2024-01-15T10:00:00Z", "timeZone": "UTC"},
            "end": {"dateTime": "2024-01-15T11:00:00Z", "timeZone": "UTC"},
            "showAs": "busy",
        })
        
        with patch.object(graph_cal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_cal_adapter.get_event("test_alias", "cal1", "evt1")
            
            assert result.id == "evt1"
            assert result.summary == "Meeting"

    def test_freebusy(self, graph_cal_adapter, mock_core):
        mock_response = MockResponse({
            "value": [
                {
                    "scheduleId": "cal1",
                    "scheduleItems": [
                        {"startTime": "2024-01-15T10:00:00Z", "endTime": "2024-01-15T11:00:00Z"},
                    ]
                }
            ]
        })
        
        with patch.object(graph_cal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            request = FreeBusyRequest(
                calendar_ids=["cal1"],
                time_min=datetime(2024, 1, 1),
                time_max=datetime(2024, 1, 31),
            )
            result = graph_cal_adapter.freebusy("test_alias", request)
            
            assert "cal1" in result.calendars
            assert len(result.calendars["cal1"]) == 1

    def test_create_event_requires_confirm_with_attendees(self, graph_cal_adapter, mock_core):
        from mailhub.calendar import Attendee
        event = Event(
            id="",
            calendar_id="cal1",
            summary="Meeting",
            attendees=(Attendee(email="test@example.com"),),
        )
        
        with pytest.raises(ValueError, match="confirm=True"):
            graph_cal_adapter.create_event("test_alias", "cal1", event, confirm=False)

    def test_create_event_no_attendees_no_confirm(self, graph_cal_adapter, mock_core):
        mock_response = MockResponse({
            "id": "new_evt",
            "subject": "Meeting",
        })
        
        with patch.object(graph_cal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            event = Event(
                id="",
                calendar_id="cal1",
                summary="Meeting",
            )
            result = graph_cal_adapter.create_event("test_alias", "cal1", event, confirm=False)
            
            assert result.id == "new_evt"

    def test_update_event(self, graph_cal_adapter, mock_core):
        mock_response = MockResponse({
            "id": "evt1",
            "subject": "Updated Meeting",
        })
        
        with patch.object(graph_cal_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            event = Event(
                id="evt1",
                calendar_id="cal1",
                summary="Updated Meeting",
            )
            result = graph_cal_adapter.update_event("test_alias", "cal1", "evt1", event, confirm=True)
            
            assert result.id == "evt1"
            assert result.summary == "Updated Meeting"

    def test_delete_event(self, graph_cal_adapter, mock_core):
        mock_get = MockResponse({
            "id": "evt1",
            "attendees": [],
        })
        mock_delete = MockResponse({}, status_code=204)
        
        with patch.object(graph_cal_adapter, '_request') as mock_request:
            mock_request.side_effect = [mock_get, mock_delete]
            graph_cal_adapter.delete_event("test_alias", "cal1", "evt1", confirm=True)
            
            assert mock_request.call_count == 2

    def test_retry_on_429(self, graph_cal_adapter, mock_core):
        call_count = [0]
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=429, headers={"Retry-After": "0"})
            return MockResponse({
                "id": "evt1", "subject": "Test",
                "start": {"dateTime": "2024-01-15T10:00:00Z", "timeZone": "UTC"},
                "end": {"dateTime": "2024-01-15T11:00:00Z", "timeZone": "UTC"},
                "showAs": "busy",
            })
        
        mock_client.request = mock_request
        graph_cal_adapter._client = mock_client
        
        result = graph_cal_adapter.get_event("test_alias", "cal1", "evt1")
        
        assert result.id == "evt1"
        assert call_count[0] == 2

    def test_401_refreshes_token(self, graph_cal_adapter, mock_core):
        call_count = [0]
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=401)
            return MockResponse({
                "id": "evt1", "subject": "Test",
                "start": {"dateTime": "2024-01-15T10:00:00Z", "timeZone": "UTC"},
                "end": {"dateTime": "2024-01-15T11:00:00Z", "timeZone": "UTC"},
                "showAs": "busy",
            })
        
        mock_client.request = mock_request
        graph_cal_adapter._client = mock_client
        
        result = graph_cal_adapter.get_event("test_alias", "cal1", "evt1")
        
        assert result.id == "evt1"
        assert call_count[0] == 2
        mock_core._refresh_access_token.assert_called_once_with("test_alias")


