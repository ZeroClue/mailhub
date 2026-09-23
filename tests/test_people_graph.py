"""Unit tests for mailhub.people_graph module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mailhub.contacts import Contact, Email
from mailhub.core import Core, RetryPolicy
from mailhub.people_graph import GraphPeopleAdapter


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
def graph_people_adapter(mock_core):
    return GraphPeopleAdapter(mock_core)


class TestGraphPeopleAdapter:
    def test_contacts(self, graph_people_adapter, mock_core):
        mock_response = MockResponse({
            "value": [
                {
                    "id": "c1",
                    "@odata.etag": "etag1",
                    "givenName": "John",
                    "surname": "Doe",
                    "displayName": "John Doe",
                    "emailAddresses": [{"address": "john@example.com", "type": "work"}],
                    "phones": [{"number": "+1-555-1234", "type": "mobile"}],
                    "homeAddress": {"street": "123 Main", "city": "NYC", "countryOrRegion": "US"},
                    "companyName": "Acme",
                    "jobTitle": "Engineer",
                    "birthday": "1990-01-15",
                    "personalNotes": "Software engineer",
                }
            ],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/contacts?$skiptoken=abc123"
        })
        
        with patch.object(graph_people_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_people_adapter.contacts("test_alias")
            
            assert len(result["contacts"]) == 1
            c = result["contacts"][0]
            assert c.id == "c1"
            assert c.names[0].given == "John"
            assert c.emails[0].value == "john@example.com"
            assert result["next_page_token"] == "abc123"

    def test_get_contact(self, graph_people_adapter, mock_core):
        mock_response = MockResponse({
            "id": "c1",
            "givenName": "Jane",
            "surname": "Smith",
        })
        
        with patch.object(graph_people_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_people_adapter.get_contact("test_alias", "c1")
            
            assert result.id == "c1"
            assert result.names[0].given == "Jane"

    def test_create_contact_requires_confirm(self, graph_people_adapter, mock_core):
        from mailhub.contacts import Contact, Name
        contact = Contact(id="", names=(Name(given="Test"),))
        
        with pytest.raises(ValueError, match="confirm=True"):
            graph_people_adapter.create_contact("test_alias", contact, confirm=False)

    def test_create_contact_success(self, graph_people_adapter, mock_core):
        mock_response = MockResponse({
            "id": "new1",
            "givenName": "New",
            "surname": "Contact",
        })
        
        with patch.object(graph_people_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            from mailhub.contacts import Contact, Name
            contact = Contact(id="", names=(Name(given="New", family="Contact"),))
            result = graph_people_adapter.create_contact("test_alias", contact, confirm=True)
            
            assert result.id == "new1"

    def test_update_contact(self, graph_people_adapter, mock_core):
        mock_response = MockResponse({
            "id": "c1",
            "givenName": "Updated",
            "surname": "Contact",
        })
        
        with patch.object(graph_people_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            from mailhub.contacts import Contact, Name
            contact = Contact(id="c1", names=(Name(given="Updated", family="Contact"),))
            result = graph_people_adapter.update_contact("test_alias", "c1", contact, confirm=True)
            
            assert result.id == "c1"
            assert result.names[0].given == "Updated"

    def test_delete_contact(self, graph_people_adapter, mock_core):
        with patch.object(graph_people_adapter, '_request') as mock_request:
            mock_request.return_value = MockResponse({}, status_code=204)
            graph_people_adapter.delete_contact("test_alias", "c1", confirm=True)
            
            mock_request.assert_called_once()

    def test_delete_contact_requires_confirm(self, graph_people_adapter, mock_core):
        with pytest.raises(ValueError, match="confirm=True"):
            graph_people_adapter.delete_contact("test_alias", "c1", confirm=False)

    def test_contact_folders(self, graph_people_adapter, mock_core):
        mock_response = MockResponse({
            "value": [
                {"id": "f1", "displayName": "Personal"},
                {"id": "f2", "displayName": "Work"},
            ]
        })
        
        with patch.object(graph_people_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_people_adapter.contact_folders("test_alias")
            
            assert len(result) == 2
            assert result[0].id == "f1"
            assert result[0].name == "Personal"

    def test_create_folder_requires_confirm(self, graph_people_adapter, mock_core):
        with pytest.raises(ValueError, match="confirm=True"):
            graph_people_adapter.create_folder("test_alias", "New Folder", confirm=False)

    def test_retry_on_429(self, graph_people_adapter, mock_core):
        call_count = [0]
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=429, headers={"Retry-After": "0"})
            return MockResponse({
                "value": [{
                    "id": "c1",
                    "givenName": "Test",
                }]
            })
        
        mock_client.request = mock_request
        graph_people_adapter._client = mock_client
        
        result = graph_people_adapter.contacts("test_alias")
        
        assert len(result["contacts"]) == 1
        assert call_count[0] == 2

    def test_401_refreshes_token(self, graph_people_adapter, mock_core):
        call_count = [0]
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=401)
            return MockResponse({
                "value": [{
                    "id": "c1",
                    "givenName": "Test",
                }]
            })
        
        mock_client.request = mock_request
        graph_people_adapter._client = mock_client
        
        result = graph_people_adapter.contacts("test_alias")
        
        assert len(result["contacts"]) == 1
        assert call_count[0] == 2
        mock_core._refresh_access_token.assert_called_once_with("test_alias")


