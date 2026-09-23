"""Contacts domain models and shared types for Mailhub M4."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class ContactSource(str, Enum):
    """Source of contact."""
    GOOGLE = "google"
    GRAPH = "graph"
    CARDDAV = "carddav"


@dataclass(frozen=True)
class Name:
    """Contact name components."""
    given: str | None = None
    family: str | None = None
    middle: str | None = None
    prefix: str | None = None
    suffix: str | None = None
    display: str | None = None


@dataclass(frozen=True)
class Email:
    """Contact email."""
    value: str
    type: str = "other"  # home, work, other
    primary: bool = False


@dataclass(frozen=True)
class Phone:
    """Contact phone."""
    value: str
    type: str = "other"  # mobile, home, work, other


@dataclass(frozen=True)
class Address:
    """Contact address."""
    street: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None
    type: str = "other"  # home, work, other
    formatted: str | None = None


@dataclass(frozen=True)
class Organization:
    """Contact organization."""
    name: str
    title: str | None = None
    department: str | None = None
    domain: str | None = None
    type: str = "work"


@dataclass(frozen=True)
class Photo:
    """Contact photo."""
    url: str
    default: bool = False


@dataclass(frozen=True)
class Contact:
    """A contact."""
    id: str
    etag: str | None = None
    names: tuple[Name, ...] = ()
    emails: tuple[Email, ...] = ()
    phones: tuple[Phone, ...] = ()
    addresses: tuple[Address, ...] = ()
    organizations: tuple[Organization, ...] = ()
    birthday: date | None = None
    notes: str | None = None
    photos: tuple[Photo, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    source: ContactSource = ContactSource.GOOGLE


@dataclass(frozen=True)
class ContactGroup:
    """A contact group."""
    id: str
    name: str
    member_ids: tuple[str, ...] = ()
    member_count: int = 0


class ContactsError(ValueError):
    """Base contacts error."""


class ContactNotFound(ContactsError):
    """Contact not found."""


class GroupNotFound(ContactsError):
    """Group not found."""


