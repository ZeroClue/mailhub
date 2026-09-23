"""Microsoft Graph Tasks/ToDo adapter for Mailhub M4."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from .tasks import (
    ListNotFound,
    Task,
    TaskList,
    TaskNotFound,
    TaskPriority,
    TaskStatus,
)
from .core import Core


GRAPH_BASE = "https://graph.microsoft.com/v1.0/me"


class GraphTasksAdapter:
    """Microsoft Graph Tasks/ToDo adapter (synchronous)."""

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

    def _parse_status(self, status: str | None) -> TaskStatus:
        if not status:
            return TaskStatus.NEEDS_ACTION
        mapping = {
            "notStarted": TaskStatus.NEEDS_ACTION,
            "inProgress": TaskStatus.IN_PROGRESS,
            "completed": TaskStatus.COMPLETED,
            "waitingOnOthers": TaskStatus.WAITING,
            "deferred": TaskStatus.DEFERRED,
        }
        return mapping.get(status, TaskStatus.NEEDS_ACTION)

    def _parse_priority(self, priority: str | None) -> TaskPriority:
        if not priority:
            return TaskPriority.MEDIUM
        mapping = {
            "low": TaskPriority.LOW,
            "normal": TaskPriority.MEDIUM,
            "high": TaskPriority.HIGH,
        }
        return mapping.get(priority, TaskPriority.MEDIUM)

    def _format_status(self, status: TaskStatus) -> str:
        reverse = {
            TaskStatus.NEEDS_ACTION: "notStarted",
            TaskStatus.IN_PROGRESS: "inProgress",
            TaskStatus.COMPLETED: "completed",
            TaskStatus.WAITING: "waitingOnOthers",
            TaskStatus.DEFERRED: "deferred",
        }
        return reverse.get(status, "notStarted")

    def _format_priority(self, priority: TaskPriority) -> str:
        reverse = {
            TaskPriority.LOW: "low",
            TaskPriority.MEDIUM: "normal",
            TaskPriority.HIGH: "high",
        }
        return reverse.get(priority, "normal")

    def _parse_task(self, data: dict, list_id: str) -> Task:
        return Task(
            id=data["id"],
            etag=data.get("@odata.etag"),
            title=data.get("title", ""),
            notes=data.get("body", {}).get("content"),
            status=self._parse_status(data.get("status")),
            due=self._parse_datetime(data.get("dueDateTime", {}).get("dateTime")) if data.get("dueDateTime") else None,
            completed=self._parse_datetime(data.get("completedDateTime")) if data.get("completedDateTime") else None,
            start=self._parse_datetime(data.get("startDateTime")) if data.get("startDateTime") else None,
            recurrence=tuple(data.get("recurrence", {}).get("pattern", {}).get("recurrenceRange", [])),
            priority=self._parse_priority(data.get("importance")),
            list_id=list_id,
            created=self._parse_datetime(data.get("createdDateTime")),
            updated=self._parse_datetime(data.get("lastModifiedDateTime")),
        )

    def _parse_list(self, data: dict) -> TaskList:
        return TaskList(
            id=data["id"],
            title=data.get("displayName", ""),
            updated=self._parse_datetime(data.get("lastModifiedDateTime")),
            color=data.get("color"),
        )

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    # --- Public API ---

    def lists(self, alias: str) -> list[TaskList]:
        """List task lists."""
        response = self._request("GET", f"{GRAPH_BASE}/todo/lists", alias)
        data = response.json()
        return [self._parse_list(l) for l in data.get("value", [])]

    def tasks(
        self,
        alias: str,
        list_id: str,
        top: int = 100,
        skip: int = 0,
    ) -> dict[str, Any]:
        """List tasks in a list."""
        params = {
            "$top": top,
            "$skip": skip,
        }
        response = self._request(
            "GET", f"{GRAPH_BASE}/todo/lists/{list_id}/tasks", alias, params=params
        )
        data = response.json()
        tasks = [self._parse_task(t, list_id) for t in data.get("value", [])]
        return {
            "tasks": tasks,
            "next_page_token": data.get("@odata.nextLink", "").split("$skiptoken=")[-1] if "@odata.nextLink" in data else None,
        }

    def get_task(self, alias: str, list_id: str, task_id: str) -> Task:
        """Get a single task."""
        response = self._request("GET", f"{GRAPH_BASE}/todo/lists/{list_id}/tasks/{task_id}", alias)
        data = response.json()
        return self._parse_task(data, list_id)

    def create_task(self, alias: str, list_id: str, task: Task, confirm: bool = False) -> Task:
        """Create a task (requires confirm)."""
        if not confirm:
            raise ValueError("create task requires confirm=True")

        body = self._task_to_body(task)
        response = self._request(
            "POST", f"{GRAPH_BASE}/todo/lists/{list_id}/tasks", alias, json_data=body
        )
        data = response.json()
        return self._parse_task(data, list_id)

    def update_task(self, alias: str, list_id: str, task_id: str, task: Task, confirm: bool = False) -> Task:
        """Update a task (requires confirm)."""
        if not confirm:
            raise ValueError("update task requires confirm=True")

        body = self._task_to_body(task)
        response = self._request(
            "PATCH", f"{GRAPH_BASE}/todo/lists/{list_id}/tasks/{task_id}", alias, json_data=body
        )
        data = response.json()
        return self._parse_task(data, list_id)

    def delete_task(self, alias: str, list_id: str, task_id: str, confirm: bool = False) -> None:
        """Delete a task (requires confirm)."""
        if not confirm:
            raise ValueError("delete task requires confirm=True")

        self._request("DELETE", f"{GRAPH_BASE}/todo/lists/{list_id}/tasks/{task_id}", alias)

    def create_list(self, alias: str, title: str, confirm: bool = False) -> TaskList:
        """Create a task list (requires confirm)."""
        if not confirm:
            raise ValueError("create list requires confirm=True")

        body = {"displayName": title}
        response = self._request("POST", f"{GRAPH_BASE}/todo/lists", alias, json_data=body)
        data = response.json()
        return self._parse_list(data)

    def _task_to_body(self, task: Task) -> dict[str, Any]:
        body: dict[str, Any] = {
            "title": task.title,
            "status": self._format_status(task.status),
            "importance": self._format_priority(task.priority),
        }
        if task.notes:
            body["body"] = {"content": task.notes, "contentType": "text"}
        if task.due:
            body["dueDateTime"] = {"dateTime": task.due.isoformat(), "timeZone": "UTC"}
        if task.start:
            body["startDateTime"] = task.start.isoformat()
        if task.recurrence:
            # Simplified - Graph recurrence is complex
            pass
        return body


