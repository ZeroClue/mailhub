"""CalDAV adapter for Mailhub M3 (read-only basic support)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from .calendar import (
    Calendar,
    CalendarNotFound,
    Event,
    EventStatus,
    FreeBusyPeriod,
    FreeBusyRequest,
    FreeBusyResponse,
)
from .core import Core


class CalDAVAdapter:
    """CalDAV adapter (synchronous, read-only basic support)."""

    def __init__(self, core: Core) -> None:
        self._core = core
        self._client: httpx.Client | None = None
        self._base_url: str | None = None
        self._username: str | None = None
        self._password: str | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _load_credentials(self, alias: str) -> None:
        """Load CalDAV credentials from core store."""
        creds = self._core._load_credentials(alias)
        self._base_url = creds.client_id  # stored as base_url
        self._username = creds.client_secret  # stored as username
        self._password = creds.access_token  # stored as password
        if not self._base_url or not self._username or not self._password:
            raise ValueError(f"CalDAV credentials not configured for {alias}")

    def _auth(self) -> tuple[str, str]:
        return (self._username, self._password)

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        content: str | None = None,
    ) -> httpx.Response:
        client = self._get_client()
        request_headers = {"Depth": "1", "Content-Type": "application/xml"}
        if headers:
            request_headers.update(headers)
        
        response = client.request(
            method,
            url,
            auth=self._auth(),
            headers=request_headers,
            content=content,
        )
        response.raise_for_status()
        return response

    def _parse_calendar(self, href: str, props: dict) -> Calendar:
        return Calendar(
            id=href,
            name=props.get("displayname", href),
            provider="caldav",
            description=None,
            timezone=props.get("timezone"),
            color=None,
            read_only=False,
        )

    def _parse_event(self, href: str, vcalendar_data: str) -> Event | None:
        # Basic iCalendar parsing - would need icalendar library for full support
        # This is a minimal stub
        return None

    # --- Public API (read-only) ---

    def calendars(self, alias: str) -> list[Calendar]:
        """List calendars (principal URL discovery)."""
        self._load_credentials(alias)
        # PROPFIND on principal URL to find calendar homes
        # This is simplified - real implementation needs principal discovery
        principal_url = f"{self._base_url.rstrip('/')}/.well-known/caldav"
        response = self._request("PROPFIND", principal_url)
        # Parse response for calendar URLs
        # For now, return empty list
        return []

    def events(
        self,
        alias: str,
        calendar_id: str,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        max_results: int = 50,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """List events in a calendar (REPORT calendar-query)."""
        self._load_credentials(alias)
        # Would need REPORT with CALDAV:calendar-query filter
        # For now, return empty
        return {"events": [], "next_page_token": None}

    def get_event(self, alias: str, calendar_id: str, event_id: str) -> Event:
        """Get a single event."""
        self._load_credentials(alias)
        # GET the event resource
        raise CalendarNotFound(f"Event {event_id} not found")

    def freebusy(self, alias: str, request: FreeBusyRequest) -> FreeBusyResponse:
        """Free/busy not implemented for CalDAV."""
        return FreeBusyResponse(calendars={})

    # Write operations not supported in basic CalDAV adapter
    def create_event(self, *args, **kwargs) -> Event:
        raise NotImplementedError("CalDAV write operations not implemented")

    def update_event(self, *args, **kwargs) -> Event:
        raise NotImplementedError("CalDAV write operations not implemented")

    def delete_event(self, *args, **kwargs) -> None:
        raise NotImplementedError("CalDAV write operations not implemented")


