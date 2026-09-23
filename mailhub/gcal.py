"""Google Calendar API adapter for Mailhub M3."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx

from .calendar import (
    Attendee,
    AttendeeStatus,
    Calendar,
    CalendarNotFound,
    Event,
    EventStatus,
    FreeBusyPeriod,
    FreeBusyRequest,
    FreeBusyResponse,
)
from .core import Core


GCAL_BASE = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarAdapter:
    """Google Calendar API adapter (synchronous)."""

    def __init__(self, core: Core) -> None:
        self._core = core
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _auth_header(self, alias: str) -> dict[str, str]:
        token = self._core._ensure_access_token(alias)
        return {"Authorization": f"Bearer {token}"}

    def _request(
        self,
        method: str,
        url: str,
        alias: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        client = self._get_client()
        request_headers = self._auth_header(alias)
        if headers:
            request_headers.update(headers)

        retry_policy = self._core._retry_policy

        for attempt in range(retry_policy.max_attempts):
            try:
                response = client.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    headers=request_headers,
                )

                if response.status_code == 401:
                    if attempt == 0:
                        self._core._refresh_access_token(alias)
                        request_headers = self._auth_header(alias)
                        if headers:
                            request_headers.update(headers)
                        continue
                    response.raise_for_status()

                if response.status_code == 429 or 500 <= response.status_code < 600:
                    if attempt < retry_policy.max_attempts - 1:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = float(retry_after)
                            except ValueError:
                                delay = retry_policy.base_delay * (2 ** attempt)
                        else:
                            delay = retry_policy.base_delay * (2 ** attempt)
                        delay = min(delay, retry_policy.max_delay)
                        import time
                        time.sleep(delay)
                        continue
                    response.raise_for_status()

                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401 and attempt == 0:
                    self._core._refresh_access_token(alias)
                    request_headers = self._auth_header(alias)
                    if headers:
                        request_headers.update(headers)
                    continue
                if e.response.status_code in (429,) or 500 <= e.response.status_code < 600:
                    if attempt < retry_policy.max_attempts - 1:
                        retry_after = e.response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = float(retry_after)
                            except ValueError:
                                delay = retry_policy.base_delay * (2 ** attempt)
                        else:
                            delay = retry_policy.base_delay * (2 ** attempt)
                        delay = min(delay, retry_policy.max_delay)
                        import time
                        time.sleep(delay)
                        continue
                raise

            except httpx.RequestError as e:
                if attempt < retry_policy.max_attempts - 1:
                    delay = retry_policy.base_delay * (2 ** attempt)
                    delay = min(delay, retry_policy.max_delay)
                    import time
                    time.sleep(delay)
                    continue
                raise

        raise RuntimeError("unreachable")

    def _parse_calendar(self, data: dict) -> Calendar:
        return Calendar(
            id=data["id"],
            name=data.get("summary", ""),
            provider="google",
            description=data.get("description"),
            timezone=data.get("timeZone"),
            color=data.get("backgroundColor"),
            read_only=data.get("accessRole") in ("reader", "freeBusyReader"),
            primary=data.get("primary", False),
        )

    def _parse_attendee(self, data: dict) -> Attendee:
        return Attendee(
            email=data.get("email", ""),
            name=data.get("displayName"),
            status=AttendeeStatus(data.get("responseStatus", "needsAction")),
            optional=data.get("optional", False),
            organizer=data.get("organizer", False),
            response_requested=data.get("responseRequested", True),
        )

    def _parse_event(self, data: dict, calendar_id: str) -> Event:
        attendees = tuple(self._parse_attendee(a) for a in data.get("attendees", []))
        
        start = data.get("start", {})
        end = data.get("end", {})
        start_dt = self._parse_datetime(start.get("dateTime") or start.get("date"))
        end_dt = self._parse_datetime(end.get("dateTime") or end.get("date"))

        return Event(
            id=data["id"],
            calendar_id=calendar_id,
            summary=data.get("summary", ""),
            description=data.get("description"),
            start=start_dt,
            end=end_dt,
            timezone=start.get("timeZone") or end.get("timeZone"),
            attendees=attendees,
            location=data.get("location"),
            recurrence=tuple(data.get("recurrence", [])),
            status=EventStatus(data.get("status", "confirmed")),
            html_link=data.get("htmlLink"),
            created=self._parse_datetime(data.get("created")),
            updated=self._parse_datetime(data.get("updated")),
            transparency=data.get("transparency", "opaque"),
            visibility=data.get("visibility", "default"),
        )

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        # Handle both RFC3339 with timezone and date-only
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            # Date only
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None

    def _format_datetime(self, dt: datetime | None) -> dict[str, str] | None:
        if dt is None:
            return None
        if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
            return {"date": dt.date().isoformat()}
        return {"dateTime": dt.isoformat()}

    # --- Public API ---

    def calendars(self, alias: str) -> list[Calendar]:
        """List calendars."""
        response = self._request("GET", f"{GCAL_BASE}/users/me/calendarList", alias)
        data = response.json()
        return [self._parse_calendar(c) for c in data.get("items", [])]

    def events(
        self,
        alias: str,
        calendar_id: str,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        max_results: int = 50,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        """List events in a calendar."""
        params: dict[str, Any] = {
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_min:
            params["timeMin"] = time_min.isoformat() + "Z"
        if time_max:
            params["timeMax"] = time_max.isoformat() + "Z"
        if page_token:
            params["pageToken"] = page_token

        response = self._request(
            "GET", f"{GCAL_BASE}/calendars/{calendar_id}/events", alias, params=params
        )
        data = response.json()
        events = [self._parse_event(e, calendar_id) for e in data.get("items", [])]
        return {
            "events": events,
            "next_page_token": data.get("nextPageToken"),
        }

    def get_event(self, alias: str, calendar_id: str, event_id: str) -> Event:
        """Get a single event."""
        response = self._request(
            "GET", f"{GCAL_BASE}/calendars/{calendar_id}/events/{event_id}", alias
        )
        data = response.json()
        return self._parse_event(data, calendar_id)

    def freebusy(self, alias: str, request: FreeBusyRequest) -> FreeBusyResponse:
        """Query free/busy."""
        items = [{"id": cal_id} for cal_id in request.calendar_ids]
        body = {
            "timeMin": request.time_min.isoformat() + "Z",
            "timeMax": request.time_max.isoformat() + "Z",
            "items": items,
        }
        response = self._request(
            "POST", f"{GCAL_BASE}/freeBusy", alias, json_data=body
        )
        data = response.json()
        calendars = {}
        for cal_id, cal_data in data.get("calendars", {}).items():
            periods = [
                FreeBusyPeriod(
                    start=self._parse_datetime(b["start"]) or datetime.min,
                    end=self._parse_datetime(b["end"]) or datetime.min,
                )
                for b in cal_data.get("busy", [])
            ]
            calendars[cal_id] = periods
        return FreeBusyResponse(calendars=calendars)

    def create_event(
        self,
        alias: str,
        calendar_id: str,
        event: Event,
        confirm: bool = False,
        send_updates: str = "all",
    ) -> Event:
        """Create an event (requires confirm if attendees)."""
        if not confirm and event.attendees:
            raise ValueError("create event with attendees requires confirm=True")

        body = self._event_to_body(event)
        params = {"sendUpdates": send_updates} if event.attendees else {}
        response = self._request(
            "POST",
            f"{GCAL_BASE}/calendars/{calendar_id}/events",
            alias,
            params=params,
            json_data=body,
        )
        data = response.json()
        return self._parse_event(data, calendar_id)

    def update_event(
        self,
        alias: str,
        calendar_id: str,
        event_id: str,
        event: Event,
        confirm: bool = False,
        send_updates: str = "all",
    ) -> Event:
        """Update an event (requires confirm if attendees)."""
        if not confirm and event.attendees:
            raise ValueError("update event with attendees requires confirm=True")

        body = self._event_to_body(event)
        params = {"sendUpdates": send_updates} if event.attendees else {}
        response = self._request(
            "PUT",
            f"{GCAL_BASE}/calendars/{calendar_id}/events/{event_id}",
            alias,
            params=params,
            json_data=body,
        )
        data = response.json()
        return self._parse_event(data, calendar_id)

    def delete_event(
        self,
        alias: str,
        calendar_id: str,
        event_id: str,
        confirm: bool = False,
        send_updates: str = "all",
    ) -> None:
        """Cancel/delete an event (requires confirm if attendees)."""
        # Check if event has attendees
        event = self.get_event(alias, calendar_id, event_id)
        if not confirm and event.attendees:
            raise ValueError("delete event with attendees requires confirm=True")

        params = {"sendUpdates": send_updates} if event.attendees else {}
        self._request(
            "DELETE",
            f"{GCAL_BASE}/calendars/{calendar_id}/events/{event_id}",
            alias,
            params=params,
        )

    def _event_to_body(self, event: Event) -> dict[str, Any]:
        body: dict[str, Any] = {
            "summary": event.summary,
        }
        if event.description:
            body["description"] = event.description
        if event.location:
            body["location"] = event.location
        if event.start:
            body["start"] = self._format_datetime(event.start)
            if event.timezone:
                body["start"]["timeZone"] = event.timezone
        if event.end:
            body["end"] = self._format_datetime(event.end)
            if event.timezone:
                body["end"]["timeZone"] = event.timezone
        if event.attendees:
            body["attendees"] = [
                {
                    "email": a.email,
                    "displayName": a.name,
                    "optional": a.optional,
                    "responseRequested": a.response_requested,
                }
                for a in event.attendees
            ]
        if event.recurrence:
            body["recurrence"] = list(event.recurrence)
        if event.transparency != "opaque":
            body["transparency"] = event.transparency
        if event.visibility != "default":
            body["visibility"] = event.visibility
        return body


