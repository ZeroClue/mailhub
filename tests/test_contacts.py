"""Unit tests for mailhub.contacts module."""

from __future__ import annotations

from datetime import date

import pytest

from mailhub.contacts import (
    Address,
    Contact,
    ContactGroup,
    Email,
    Name,
    Organization,
    Phone,
    Photo,
    ContactSource,
)


class TestContact:
    def test_contact_minimal(self):
        c = Contact(id="c1")
        assert c.id == "c1"
        assert c.source == ContactSource.GOOGLE

    def test_contact_with_names(self):
        name = Name(given="John", family="Doe", display="John Doe")
        c = Contact(id="c1", names=(name,))
        assert c.names[0].given == "John"
        assert c.names[0].display == "John Doe"

    def test_contact_with_emails(self):
        email = Email(value="john@example.com", type="work", primary=True)
        c = Contact(id="c1", emails=(email,))
        assert c.emails[0].value == "john@example.com"

    def test_contact_with_phones(self):
        phone = Phone(value="+1-555-1234", type="mobile")
        c = Contact(id="c1", phones=(phone,))
        assert c.phones[0].value == "+1-555-1234"

    def test_contact_with_addresses(self):
        addr = Address(street="123 Main St", city="NYC", country="USA", type="home")
        c = Contact(id="c1", addresses=(addr,))
        assert c.addresses[0].city == "NYC"

    def test_contact_with_organizations(self):
        org = Organization(name="Acme Corp", title="Engineer", type="work")
        c = Contact(id="c1", organizations=(org,))
        assert c.organizations[0].name == "Acme Corp"

    def test_contact_with_birthday(self):
        c = Contact(id="c1", birthday=date(1990, 1, 15))
        assert c.birthday == date(1990, 1, 15)


class TestContactGroup:
    def test_group_creation(self):
        g = ContactGroup(id="g1", name="Family", member_ids=("c1", "c2"), member_count=2)
        assert g.name == "Family"
        assert g.member_count == 2


