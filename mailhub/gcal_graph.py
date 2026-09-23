"""Microsoft Graph Calendar API adapter for Mailhub M3."""

from __future__ import annotations

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


GRAPH_BASE = "https://graph.microsoft.com/v1.0/me"


class GraphCalendarAdapter:
    """Microsoft Graph Calendar API adapter (synchronous)."""

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
            name=data.get("name", ""),
            provider="graph",
            description=None,
            timezone=None,
            color=data.get("color"),
            read_only=False,
            primary=data.get("isDefaultCalendar", False),
        )

    def _parse_attendee(self, data: dict) -> Attendee:
        status_map = {
            "none": AttendeeStatus.NEEDS_ACTION,
            "accepted": AttendeeStatus.ACCEPTED,
            "declined": AttendeeStatus.DECLINED,
            "tentativelyAccepted": AttendeeStatus.TENTATIVE,
        }
        email_addr = data.get("emailAddress", {})
        return Attendee(
            email=email_addr.get("address", ""),
            name=email_addr.get("name"),
            status=status_map.get(data.get("status", {}).get("response", "none"), AttendeeStatus.NEEDS_ACTION),
            optional=data.get("type") == "optional",
            organizer=False,
            response_requested=True,
        )

    def _parse_event(self, data: dict, calendar_id: str) -> Event:
        attendees = tuple(self._parse_attendee(a) for a in data.get("attendees", []))
        
        start = data.get("start", {})
        end = data.get("end", {})
        start_dt = self._parse_datetime(start.get("dateTime"))
        end_dt = self._parse_datetime(end.get("dateTime"))

        return Event(
            id=data["id"],
            calendar_id=calendar_id,
            summary=data.get("subject", ""),
            description=data.get("bodyPreview"),
            start=start_dt,
            end=end_dt,
            timezone=start.get("timeZone"),
            attendees=attendees,
            location=data.get("location", {}).get("displayName"),
            recurrence=tuple(data.get("recurrence", {}).get("pattern", {}).get("recurrenceRange", {}).get("recurrenceRange", [])),
            status=EventStatus(data.get("showAs", "confirmed").lower()),
            html_link=data.get("webLink"),
            created=self._parse_datetime(data.get("createdDateTime")),
            updated=self._parse_datetime(data.get("lastModifiedDateTime")),
        )

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _format_datetime(self, dt: datetime | None) -> dict[str, str] | None:
        if dt is None:
            return None
        return {"dateTime": dt.isoformat(), "timeZone": "UTC"}

    # --- Public API ---

    def calendars(self, alias: str) -> list[Calendar]:
        """List calendars."""
        response = self._request("GET", f"{GRAPH_BASE}/calendars", alias)
        data = response.json()
        return [self._parse_calendar(c) for c in data.get("value", [])]

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
            "$top": max_results,
            "$orderby": "start/dateTime",
        }
        if time_min:
            params["$filter"] = f"start/dateTime ge '{time_min.isoformat()}Z'"
        if page_token:
            params["$skiptoken"] = page_token

        response = self._request(
            "GET", f"{GRAPH_BASE}/calendars/{calendar_id}/events", alias, params=params
        )
        data = response.json()
        events = [self._parse_event(e, calendar_id) for e in data.get("value", [])]
        return {
            "events": events,
            "next_page_token": data.get("@odata.nextLink", "").split("$skiptoken=")[-1] if "@odata.nextLink" in data else None,
        }

    def get_event(self, alias: str, calendar_id: str, event_id: str) -> Event:
        """Get a single event."""
        response = self._request("GET", f"{GRAPH_BASE}/calendars/{calendar_id}/events/{event_id}", alias)
        data = response.json()
        return self._parse_event(data, calendar_id)

    def freebusy(self, alias: str, request: FreeBusyRequest) -> FreeBusyResponse:
        """Query free/busy via getSchedule."""
        schedules = [{"scheduleId": cal_id} for cal_id in request.calendar_ids]
        body = {
            "schedules": schedules,
            "startTime": {"dateTime": request.time_min.isoformat() + "Z", "timeZone": "UTC"},
            "endTime": {"dateTime": request.time_max.isoformat() + "Z", "timeZone": "UTC"},
            "availabilityViewInterval": 30,
        }
        response = self._request("POST", f"{GRAPH_BASE}/getSchedule", alias, json_data=body)
        data = response.json()
        calendars = {}
        for sched in data.get("value", []):
            cal_id = sched.get("scheduleId", "")
            periods = [
                FreeBusyPeriod(
                    start=self._parse_datetime(s["startTime"]) or datetime.min,
                    end=self._parse_datetime(s["endTime"]) or datetime.min,
                )
                for s in sched.get("scheduleItems", [])
            ]
            calendars[cal_id] = periods
        return FreeBusyResponse(calendars=calendars)

    def create_event(
        self,
        alias: str,
        calendar_id: str,
        event: Event,
        confirm: bool = False,
        send_updates: str = "sendToAllAndSaveCopy",
    ) -> Event:
        """Create an event (requires confirm if attendees)."""
        if not confirm and event.attendees:
            raise ValueError("create event with attendees requires confirm=True")

        body = self._event_to_body(event)
        response = self._request(
            "POST",
            f"{GRAPH_BASE}/calendars/{calendar_id}/events",
            alias,
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
        send_updates: str = "sendToAllAndSaveCopy",
    ) -> Event:
        """Update an event (requires confirm if attendees)."""
        if not confirm and event.attendees:
            raise ValueError("update event with attendees requires confirm=True")

        body = self._event_to_body(event)
        response = self._request(
            "PATCH",
            f"{GRAPH_BASE}/calendars/{calendar_id}/events/{event_id}",
            alias,
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
    ) -> None:
        """Cancel/delete an event (requires confirm if attendees)."""
        event = self.get_event(alias, calendar_id, event_id)
        if not confirm and event.attendees:
            raise ValueError("delete event with attendees requires confirm=True")

        self._request("DELETE", f"{GRAPH_BASE}/calendars/{calendar_id}/events/{event_id}", alias)

    def _event_to_body(self, event: Event) -> dict[str, Any]:
        body: dict[str, Any] = {
            "subject": event.summary,
        }
        if event.description:
            body["body"] = {"contentType": "text", "content": event.description}
        if event.location:
            body["location"] = {"displayName": event.location}
        if event.start:
            body["start"] = self._format_datetime(event.start)
        if event.end:
            body["end"] = self._format_datetime(event.end)
        if event.attendees:
            body["attendees"] = [
                {
                    "emailAddress": {"address": a.email, "name": a.name},
                    "type": "optional" if a.optional else "required",
                }
                for a in event.attendees
            ]
        if event.recurrence:
            # Graph recurrence is complex - simplified
            pass
        return body


