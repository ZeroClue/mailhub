"""Unit tests for mailhub.calendar module."""

from __future__ import annotations

from datetime import datetime

import pytest

from mailhub.calendar import (
    Attendee,
    AttendeeStatus,
    Calendar,
    Event,
    EventStatus,
    FreeBusyPeriod,
    FreeBusyRequest,
    FreeBusyResponse,
)


class TestCalendar:
    def test_calendar_creation(self):
        cal = Calendar(
            id="cal1",
            name="Personal",
            provider="google",
            description="My calendar",
            timezone="America/New_York",
            color="#ff0000",
            primary=True,
        )
        assert cal.id == "cal1"
        assert cal.name == "Personal"
        assert cal.primary is True


class TestAttendee:
    def test_attendee_defaults(self):
        att = Attendee(email="test@example.com")
        assert att.email == "test@example.com"
        assert att.status == AttendeeStatus.NEEDS_ACTION
        assert att.optional is False

    def test_attendee_with_all_fields(self):
        att = Attendee(
            email="test@example.com",
            name="Test User",
            status=AttendeeStatus.ACCEPTED,
            optional=True,
            organizer=True,
        )
        assert att.name == "Test User"
        assert att.status == AttendeeStatus.ACCEPTED
        assert att.optional is True
        assert att.organizer is True


class TestEvent:
    def test_event_minimal(self):
        evt = Event(
            id="evt1",
            calendar_id="cal1",
            summary="Meeting",
        )
        assert evt.id == "evt1"
        assert evt.summary == "Meeting"
        assert evt.status == EventStatus.CONFIRMED

    def test_event_with_attendees(self):
        att = Attendee(email="test@example.com", status=AttendeeStatus.ACCEPTED)
        evt = Event(
            id="evt1",
            calendar_id="cal1",
            summary="Meeting",
            attendees=(att,),
            start=datetime(2024, 1, 15, 10, 0),
            end=datetime(2024, 1, 15, 11, 0),
        )
        assert len(evt.attendees) == 1
        assert evt.attendees[0].email == "test@example.com"


class TestFreeBusy:
    def test_freebusy_request(self):
        req = FreeBusyRequest(
            calendar_ids=["cal1", "cal2"],
            time_min=datetime(2024, 1, 1),
            time_max=datetime(2024, 1, 31),
        )
        assert len(req.calendar_ids) == 2

    def test_freebusy_response(self):
        periods = [
            FreeBusyPeriod(
                start=datetime(2024, 1, 15, 10, 0),
                end=datetime(2024, 1, 15, 11, 0),
            )
        ]
        resp = FreeBusyResponse(calendars={"cal1": periods})
        assert "cal1" in resp.calendars
        assert len(resp.calendars["cal1"]) == 1


