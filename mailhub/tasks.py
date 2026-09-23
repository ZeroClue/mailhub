"""Tasks domain models and shared types for Mailhub M4."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    """Task status values."""
    NEEDS_ACTION = "needsAction"
    COMPLETED = "completed"
    IN_PROGRESS = "inProgress"
    WAITING = "waiting"
    DEFERRED = "deferred"


class TaskPriority(str, Enum):
    """Task priority values."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    # Graph-specific
    NORMAL = "normal"
    URGENT = "urgent"


@dataclass(frozen=True)
class Reminder:
    """Task reminder."""
    trigger: datetime
    method: str = "display"  # display, email


@dataclass(frozen=True)
class Task:
    """A task."""
    id: str
    etag: str | None = None
    title: str = ""
    notes: str | None = None
    status: TaskStatus = TaskStatus.NEEDS_ACTION
    due: datetime | None = None
    completed: datetime | None = None
    start: datetime | None = None
    recurrence: tuple[str, ...] = ()
    reminders: tuple[Reminder, ...] = ()
    priority: TaskPriority = TaskPriority.MEDIUM
    list_id: str | None = None
    created: datetime | None = None
    updated: datetime | None = None


@dataclass(frozen=True)
class TaskList:
    """A task list."""
    id: str
    title: str
    updated: datetime | None = None
    color: str | None = None


class TasksError(ValueError):
    """Base tasks error."""


class TaskNotFound(TasksError):
    """Task not found."""


class ListNotFound(TasksError):
    """Task list not found."""


