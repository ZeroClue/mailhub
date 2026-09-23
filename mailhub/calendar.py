"""Calendar domain models and shared types for Mailhub M3."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventStatus(str, Enum):
    """Event status values."""
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"
    # Graph-specific
    BUSY = "busy"
    FREE = "free"
    OUT_OF_OFFICE = "outOfOffice"
    WORKING_ELSEWHERE = "workingElsewhere"


class AttendeeStatus(str, Enum):
    """Attendee response status."""
    NEEDS_ACTION = "needsAction"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    TENTATIVE = "tentative"


@dataclass(frozen=True)
class Calendar:
    """A calendar."""
    id: str
    name: str
    provider: str
    description: str | None = None
    timezone: str | None = None
    color: str | None = None
    read_only: bool = False
    primary: bool = False


@dataclass(frozen=True)
class Attendee:
    """An event attendee."""
    email: str
    name: str | None = None
    status: AttendeeStatus = AttendeeStatus.NEEDS_ACTION
    optional: bool = False
    organizer: bool = False
    response_requested: bool = True


@dataclass(frozen=True)
class Event:
    """A calendar event."""
    id: str
    calendar_id: str
    summary: str
    description: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    timezone: str | None = None
    attendees: tuple[Attendee, ...] = ()
    location: str | None = None
    recurrence: tuple[str, ...] = ()
    status: EventStatus = EventStatus.CONFIRMED
    html_link: str | None = None
    created: datetime | None = None
    updated: datetime | None = None
    creator: Attendee | None = None
    organizer: Attendee | None = None
    transparency: str = "opaque"  # opaque or transparent
    visibility: str = "default"   # default, public, private, confidential


@dataclass(frozen=True)
class FreeBusyRequest:
    """Free/busy query request."""
    calendar_ids: list[str]
    time_min: datetime
    time_max: datetime


@dataclass(frozen=True)
class FreeBusyPeriod:
    """A busy period from free/busy query."""
    start: datetime
    end: datetime


@dataclass(frozen=True)
class FreeBusyResponse:
    """Free/busy query response."""
    calendars: dict[str, list[FreeBusyPeriod]]


class CalendarError(ValueError):
    """Base calendar error."""


class CalendarNotFound(CalendarError):
    """Calendar not found."""


class EventNotFound(CalendarError):
    """Event not found."""


class CalendarAuthError(CalendarError):
    """Calendar authentication error."""


