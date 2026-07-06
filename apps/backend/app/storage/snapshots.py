"""Service layer: apply a patch to the stored plan with undo support.

Keeps the snapshot/undo policy in one place so both the REST API and the MCP
tools go through the same path:

    validate  -> compute diff WITHOUT persisting  (dry-run)
    apply     -> snapshot current, persist new, return diff
    undo      -> pop snapshot

The domain stays pure (patches.apply_patch never touches storage); this module
is the only place that knows about persistence + versioning together.
"""

from __future__ import annotations

from datetime import date

from ..domain.models import Diff, Patch, Plan
from ..domain.patches import apply_patch
from .db import Storage


def validate_patch(storage: Storage, patch: Patch, project_start: date | None = None) -> Diff:
    """Dry-run: returns the diff (or raises PlanValidationError). No write."""
    current = storage.get_plan()
    _, diff = apply_patch(current, patch, project_start)
    return diff


def apply_and_commit(storage: Storage, patch: Patch, project_start: date | None = None) -> Diff:
    """Apply atomically, snapshot the old plan, persist the new plan."""
    current = storage.get_plan()
    new_plan, diff = apply_patch(current, patch, project_start)
    storage.commit_plan(new_plan)  # pushes snapshot of `current`, saves new_plan
    return diff


def undo(storage: Storage) -> Plan:
    """Restore the previous snapshot as the current plan."""
    return storage.undo_last()
