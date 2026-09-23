"""Unit tests for mailhub.people module."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from mailhub.contacts import Contact, Email, Name, Phone
from mailhub.core import Core, RetryPolicy
from mailhub.people import GooglePeopleAdapter


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
def people_adapter(mock_core):
    return GooglePeopleAdapter(mock_core)


class TestGooglePeopleAdapter:
    def test_contacts(self, people_adapter, mock_core):
        mock_response = MockResponse({
            "connections": [
                {
                    "resourceName": "people/c1",
                    "etag": "etag1",
                    "names": [{"givenName": "John", "familyName": "Doe", "displayName": "John Doe"}],
                    "emailAddresses": [{"value": "john@example.com", "type": "work", "primary": True}],
                    "phoneNumbers": [{"value": "+1-555-1234", "type": "mobile"}],
                    "addresses": [{"streetAddress": "123 Main", "city": "NYC", "country": "US", "type": "home"}],
                    "organizations": [{"name": "Acme", "title": "Engineer", "type": "work"}],
                    "birthdays": [{"date": {"year": 1990, "month": 1, "day": 15}}],
                    "biographies": [{"value": "Software engineer"}],
                    "photos": [{"url": "https://example.com/photo.jpg", "default": True}],
                    "metadata": {"sources": [{"type": "CONTACT"}]},
                }
            ],
            "nextPageToken": "next_token"
        })
        
        with patch.object(people_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = people_adapter.contacts("test_alias")
            
            assert len(result["contacts"]) == 1
            c = result["contacts"][0]
            assert c.id == "c1"
            assert c.names[0].given == "John"
            assert c.emails[0].value == "john@example.com"
            assert c.phones[0].value == "+1-555-1234"
            assert c.addresses[0].city == "NYC"
            assert c.organizations[0].name == "Acme"
            assert c.birthday == date(1990, 1, 15)
            assert c.notes == "Software engineer"
            assert result["next_page_token"] == "next_token"

    def test_get_contact(self, people_adapter, mock_core):
        mock_response = MockResponse({
            "resourceName": "people/c1",
            "names": [{"givenName": "Jane", "familyName": "Smith", "displayName": "Jane Smith"}],
        })
        
        with patch.object(people_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = people_adapter.get_contact("test_alias", "people/c1")
            
            assert result.id == "c1"
            assert result.names[0].given == "Jane"

    def test_create_contact_requires_confirm(self, people_adapter, mock_core):
        contact = Contact(id="", names=(Name(given="Test"),))
        
        with pytest.raises(ValueError, match="confirm=True"):
            people_adapter.create_contact("test_alias", contact, confirm=False)

    def test_create_contact_success(self, people_adapter, mock_core):
        mock_response = MockResponse({
            "resourceName": "people/new1",
            "names": [{"givenName": "New", "familyName": "Contact"}],
        })
        
        with patch.object(people_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            contact = Contact(id="", names=(Name(given="New", family="Contact"),))
            result = people_adapter.create_contact("test_alias", contact, confirm=True)
            
            assert result.id == "new1"

    def test_update_contact_requires_confirm(self, people_adapter, mock_core):
        contact = Contact(id="c1", etag="etag1", names=(Name(given="Test"),))
        
        with pytest.raises(ValueError, match="confirm=True"):
            people_adapter.update_contact("test_alias", "people/c1", contact, confirm=False)

    def test_delete_contact_requires_confirm(self, people_adapter, mock_core):
        with pytest.raises(ValueError, match="confirm=True"):
            people_adapter.delete_contact("test_alias", "people/c1", confirm=False)

    def test_groups(self, people_adapter, mock_core):
        mock_response = MockResponse({
            "contactGroups": [
                {"resourceName": "contactGroups/g1", "name": "Family", "memberCount": 3},
                {"resourceName": "contactGroups/g2", "name": "Work", "memberCount": 5},
            ]
        })
        
        with patch.object(people_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = people_adapter.groups("test_alias")
            
            assert len(result) == 2
            assert result[0].id == "g1"
            assert result[0].name == "Family"
            assert result[0].member_count == 3

    def test_create_group_requires_confirm(self, people_adapter, mock_core):
        with pytest.raises(ValueError, match="confirm=True"):
            people_adapter.create_group("test_alias", "New Group", confirm=False)

    def test_add_to_group_requires_confirm(self, people_adapter, mock_core):
        with pytest.raises(ValueError, match="confirm=True"):
            people_adapter.add_to_group("test_alias", "g1", ["c1", "c2"], confirm=False)

    def test_retry_on_429(self, people_adapter, mock_core):
        call_count = [0]
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=429, headers={"Retry-After": "0"})
            return MockResponse({
                "connections": [{
                    "resourceName": "people/c1",
                    "names": [{"givenName": "Test"}],
                }]
            })
        
        mock_client.request = mock_request
        people_adapter._client = mock_client
        
        result = people_adapter.contacts("test_alias")
        
        assert len(result["contacts"]) == 1
        assert call_count[0] == 2

    def test_401_refreshes_token(self, people_adapter, mock_core):
        call_count = [0]
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=401)
            return MockResponse({
                "connections": [{
                    "resourceName": "people/c1",
                    "names": [{"givenName": "Test"}],
                }]
            })
        
        mock_client.request = mock_request
        people_adapter._client = mock_client
        
        result = people_adapter.contacts("test_alias")
        
        assert len(result["contacts"]) == 1
        assert call_count[0] == 2
        mock_core._refresh_access_token.assert_called_once_with("test_alias")


