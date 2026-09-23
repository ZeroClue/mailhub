"""Unit tests for mailhub.tasks_caldav module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mailhub.tasks_caldav import CalDAVTasksAdapter
from mailhub.tasks import TaskNotFound, ListNotFound


class TestCalDAVTasksAdapter:
    def test_not_implemented_write_operations(self):
        mock_core = MagicMock()
        adapter = CalDAVTasksAdapter(mock_core)
        
        with pytest.raises(NotImplementedError):
            adapter.create_task()
        
        with pytest.raises(NotImplementedError):
            adapter.update_task()
        
        with pytest.raises(NotImplementedError):
            adapter.delete_task()

    def test_read_operations_return_empty(self):
        mock_core = MagicMock()
        mock_creds = MagicMock()
        mock_creds.client_id = "http://example.com"
        mock_creds.client_secret = "user"
        mock_creds.access_token = "pass"
        mock_core._load_credentials.return_value = mock_creds
        
        adapter = CalDAVTasksAdapter(mock_core)
        
        assert adapter.lists("test_alias") == []
        assert adapter.tasks("test_alias", "cal1") == []
        
        with pytest.raises(TaskNotFound):
            adapter.get_task("test_alias", "cal1", "t1")


