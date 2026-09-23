"""Unit tests for mailhub.tasks_graph module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mailhub.tasks import Task, TaskList, TaskNotFound, ListNotFound, TaskPriority, TaskStatus
from mailhub.core import Core, RetryPolicy
from mailhub.tasks_graph import GraphTasksAdapter


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
def graph_tasks_adapter(mock_core):
    return GraphTasksAdapter(mock_core)


class TestGraphTasksAdapter:
    def test_lists(self, graph_tasks_adapter, mock_core):
        mock_response = MockResponse({
            "value": [
                {"id": "l1", "displayName": "Personal", "lastModifiedDateTime": "2024-01-01T00:00:00Z", "color": "blue"},
                {"id": "l2", "displayName": "Work", "lastModifiedDateTime": "2024-01-02T00:00:00Z", "color": "red"},
            ]
        })
        
        with patch.object(graph_tasks_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_tasks_adapter.lists("test_alias")
            
            assert len(result) == 2
            assert result[0].id == "l1"
            assert result[0].title == "Personal"
            assert result[1].id == "l2"
            assert result[1].title == "Work"

    def test_tasks(self, graph_tasks_adapter, mock_core):
        mock_response = MockResponse({
            "value": [
                {
                    "id": "t1",
                    "title": "Task 1",
                    "status": "notStarted",
                    "importance": "high",
                    "dueDateTime": {"dateTime": "2024-12-31T23:59:00Z", "timeZone": "UTC"},
                    "body": {"content": "Notes", "contentType": "text"},
                },
                {
                    "id": "t2",
                    "title": "Task 2",
                    "status": "completed",
                    "importance": "normal",
                    "completedDateTime": "2024-01-15T10:00:00Z",
                },
            ],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/todo/lists/l1/tasks?$skiptoken=abc123"
        })
        
        with patch.object(graph_tasks_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_tasks_adapter.tasks("test_alias", "l1")
            
            assert len(result["tasks"]) == 2
            assert result["tasks"][0].id == "t1"
            assert result["tasks"][0].priority == TaskPriority.HIGH
            assert result["tasks"][1].status == TaskStatus.COMPLETED
            assert result["next_page_token"] == "abc123"

    def test_get_task(self, graph_tasks_adapter, mock_core):
        mock_response = MockResponse({
            "id": "t1",
            "title": "Test Task",
            "status": "inProgress",
            "importance": "low",
        })
        
        with patch.object(graph_tasks_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_tasks_adapter.get_task("test_alias", "l1", "t1")
            
            assert result.id == "t1"
            assert result.status == TaskStatus.IN_PROGRESS
            assert result.priority == TaskPriority.LOW

    def test_create_task_requires_confirm(self, graph_tasks_adapter, mock_core):
        task = Task(id="", title="New Task")
        
        with pytest.raises(ValueError, match="confirm=True"):
            graph_tasks_adapter.create_task("test_alias", "l1", task, confirm=False)

    def test_create_task_success(self, graph_tasks_adapter, mock_core):
        mock_response = MockResponse({
            "id": "new1",
            "title": "Created Task",
            "status": "notStarted",
        })
        
        with patch.object(graph_tasks_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            task = Task(id="", title="Created Task")
            result = graph_tasks_adapter.create_task("test_alias", "l1", task, confirm=True)
            
            assert result.id == "new1"

    def test_update_task(self, graph_tasks_adapter, mock_core):
        mock_response = MockResponse({
            "id": "t1",
            "title": "Updated Task",
            "status": "completed",
        })
        
        with patch.object(graph_tasks_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            task = Task(id="t1", title="Updated Task", status=TaskStatus.COMPLETED)
            result = graph_tasks_adapter.update_task("test_alias", "l1", "t1", task, confirm=True)
            
            assert result.id == "t1"
            assert result.status == TaskStatus.COMPLETED

    def test_delete_task(self, graph_tasks_adapter, mock_core):
        with patch.object(graph_tasks_adapter, '_request') as mock_request:
            mock_request.return_value = MockResponse({}, status_code=204)
            graph_tasks_adapter.delete_task("test_alias", "l1", "t1", confirm=True)
            
            mock_request.assert_called_once()

    def test_delete_task_requires_confirm(self, graph_tasks_adapter, mock_core):
        with pytest.raises(ValueError, match="confirm=True"):
            graph_tasks_adapter.delete_task("test_alias", "l1", "t1", confirm=False)

    def test_create_list(self, graph_tasks_adapter, mock_core):
        mock_response = MockResponse({
            "id": "new_list",
            "displayName": "New List",
        })
        
        with patch.object(graph_tasks_adapter, '_request') as mock_request:
            mock_request.return_value = mock_response
            result = graph_tasks_adapter.create_list("test_alias", "New List", confirm=True)
            
            assert result.id == "new_list"
            assert result.title == "New List"

    def test_create_list_requires_confirm(self, graph_tasks_adapter, mock_core):
        with pytest.raises(ValueError, match="confirm=True"):
            graph_tasks_adapter.create_list("test_alias", "New List", confirm=False)

    def test_retry_on_429(self, graph_tasks_adapter, mock_core):
        call_count = [0]
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=429, headers={"Retry-After": "0"})
            return MockResponse({
                "value": [{"id": "t1", "title": "Test"}]
            })
        
        mock_client.request = mock_request
        graph_tasks_adapter._client = mock_client
        
        result = graph_tasks_adapter.tasks("test_alias", "l1")
        
        assert len(result["tasks"]) == 1
        assert call_count[0] == 2

    def test_401_refreshes_token(self, graph_tasks_adapter, mock_core):
        call_count = [0]
        mock_client = MagicMock()
        
        def mock_request(method, url, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MockResponse({}, status_code=401)
            return MockResponse({
                "value": [{"id": "t1", "title": "Test"}]
            })
        
        mock_client.request = mock_request
        graph_tasks_adapter._client = mock_client
        
        result = graph_tasks_adapter.tasks("test_alias", "l1")
        
        assert len(result["tasks"]) == 1
        assert call_count[0] == 2
        mock_core._refresh_access_token.assert_called_once_with("test_alias")


