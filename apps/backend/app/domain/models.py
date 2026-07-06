"""Pydantic v2 domain models.

Design note — "dates are derived, never stored":
    `Task` holds only *inputs* to scheduling (duration, dependencies, and an
    optional `offset_days` lag). It deliberately has NO `start`/`end` fields.
    The scheduler computes concrete dates on demand and returns them wrapped in
    `ScheduledTask`. `offset_days` is a scheduling *input* (like `duration_days`),
    not a stored date, so the "dates are derived" invariant still holds — it lets
    the `shift_task` operation push a task later without making a date the source
    of truth.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

# --- Core plan structure --------------------------------------------------


class Task(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    assignee: Optional[str] = None
    duration_days: int = Field(ge=1)
    predecessor_ids: list[str] = Field(default_factory=list)
    # Scheduling lag in calendar days (>= 0). Input to the scheduler, not a
    # stored date. Enables `shift_task` while keeping start/end derived.
    offset_days: int = Field(default=0, ge=0)


class Plan(BaseModel):
    version: int = 0
    tasks: list[Task] = Field(default_factory=list)

    def by_id(self, task_id: str) -> Optional[Task]:
        return next((t for t in self.tasks if t.id == task_id), None)


# --- Scheduled (derived) views -------------------------------------------


class ScheduledTask(Task):
    start: date
    end: date


class ScheduledPlan(BaseModel):
    version: int
    project_start: date
    tasks: list[ScheduledTask]

    def by_id(self, task_id: str) -> Optional[ScheduledTask]:
        return next((t for t in self.tasks if t.id == task_id), None)


# --- Patch / operation model ---------------------------------------------

OpType = Literal[
    "add_task",
    "update_task",
    "delete_task",
    "shift_task",
    "reassign",
    "set_dependencies",
]


class Selector(BaseModel):
    """Targets zero or more existing tasks. Exactly one field should be set."""

    by_id: Optional[str] = None
    by_name: Optional[str] = None
    by_assignee: Optional[str] = None


class Op(BaseModel):
    type: OpType
    selector: Optional[Selector] = None
    payload: dict = Field(default_factory=dict)


class Patch(BaseModel):
    ops: list[Op] = Field(default_factory=list)


# --- Diff (before/after) --------------------------------------------------

ChangeKind = Literal["added", "updated", "removed"]


class TaskDiff(BaseModel):
    id: str
    change: ChangeKind
    before: Optional[ScheduledTask] = None
    after: Optional[ScheduledTask] = None


class Diff(BaseModel):
    version_before: int
    version_after: int
    tasks: list[TaskDiff] = Field(default_factory=list)
    # Non-fatal advisories for the agent/user (e.g. "deleting X orphans Y").
    warnings: list[str] = Field(default_factory=list)
