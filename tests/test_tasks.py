"""Unit tests for mailhub.tasks module."""

from __future__ import annotations

from datetime import datetime

import pytest

from mailhub.tasks import (
    ListNotFound,
    Task,
    TaskList,
    TaskNotFound,
    TaskPriority,
    TaskStatus,
)


class TestTask:
    def test_task_minimal(self):
        t = Task(id="t1", title="Test task")
        assert t.id == "t1"
        assert t.title == "Test task"
        assert t.status == TaskStatus.NEEDS_ACTION
        assert t.priority == TaskPriority.MEDIUM

    def test_task_with_due_date(self):
        t = Task(id="t1", title="Task", due=datetime(2024, 12, 31, 23, 59))
        assert t.due == datetime(2024, 12, 31, 23, 59)

    def test_task_completed(self):
        t = Task(
            id="t1",
            title="Done",
            status=TaskStatus.COMPLETED,
            completed=datetime(2024, 1, 15, 10, 0),
        )
        assert t.status == TaskStatus.COMPLETED
        assert t.completed == datetime(2024, 1, 15, 10, 0)

    def test_task_with_recurrence(self):
        t = Task(id="t1", title="Weekly", recurrence=("RRULE:FREQ=WEEKLY",))
        assert len(t.recurrence) == 1

    def test_task_priority(self):
        t = Task(id="t1", title="Urgent", priority=TaskPriority.HIGH)
        assert t.priority == TaskPriority.HIGH


class TestTaskList:
    def test_list_creation(self):
        lst = TaskList(id="l1", title="Personal", updated=datetime(2024, 1, 1))
        assert lst.id == "l1"
        assert lst.title == "Personal"


