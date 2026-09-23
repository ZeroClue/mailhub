"""Unit tests for mailhub.carddav module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mailhub.carddav import CardDAVAdapter
from mailhub.contacts import ContactNotFound


class TestCardDAVAdapter:
    def test_not_implemented_write_operations(self):
        mock_core = MagicMock()
        adapter = CardDAVAdapter(mock_core)
        
        with pytest.raises(NotImplementedError):
            adapter.create_contact()
        
        with pytest.raises(NotImplementedError):
            adapter.update_contact()
        
        with pytest.raises(NotImplementedError):
            adapter.delete_contact()

    def test_read_operations_return_empty(self):
        mock_core = MagicMock()
        mock_creds = MagicMock()
        mock_creds.client_id = "http://example.com"
        mock_creds.client_secret = "user"
        mock_creds.access_token = "pass"
        mock_core._load_credentials.return_value = mock_creds
        
        adapter = CardDAVAdapter(mock_core)
        
        # contacts() returns empty list when no data to parse
        assert adapter.contacts("test_alias") == []
        
        with pytest.raises(ContactNotFound):
            adapter.get_contact("test_alias", "href")


