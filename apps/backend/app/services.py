"""Application services shared by the MCP tools and the REST routes.

One code path for every mutation so behaviour can't drift between "the agent did
it" and "the user clicked it". Each successful mutation broadcasts
`{"version", "diff"}` on the event bus for WebSocket clients.

Errors are returned as structured dicts ({"ok": False, "error", "code"}) rather
than raised, because the MCP tools hand these straight back to the LLM so it can
correct itself.
"""

from __future__ import annotations

from datetime import date

from .domain.models import Patch, Plan
from .domain.patches import apply_patch, compute_diff
from .domain.validators import PlanValidationError
from .events import EventBus
from .excel import scheduled_plan
from .storage.db import Storage


def _plan_view(plan: Plan, project_start: date) -> dict:
    return scheduled_plan(plan, project_start).model_dump(mode="json")


def get_plan_view(storage: Storage, project_start: date) -> dict:
    return _plan_view(storage.get_plan(), project_start)


def validate(storage: Storage, patch: Patch, project_start: date) -> dict:
    """Dry-run: returns the diff without persisting, or a structured error."""
    try:
        current = storage.get_plan()
        _, diff = apply_patch(current, patch, project_start)
    except PlanValidationError as exc:
        return {"ok": False, "error": exc.message, "code": exc.code}
    return {"ok": True, "diff": diff.model_dump(mode="json")}


async def apply(
    storage: Storage, patch: Patch, project_start: date, bus: EventBus | None
) -> dict:
    """Apply atomically, snapshot, persist, broadcast. Structured error on fail."""
    try:
        current = storage.get_plan()
        new_plan, diff = apply_patch(current, patch, project_start)
    except PlanValidationError as exc:
        return {"ok": False, "error": exc.message, "code": exc.code}
    storage.commit_plan(new_plan)
    if bus is not None:
        await bus.publish({"version": new_plan.version, "diff": diff.model_dump(mode="json")})
    return {"ok": True, "diff": diff.model_dump(mode="json")}


async def undo(storage: Storage, project_start: date, bus: EventBus | None) -> dict:
    """Restore the previous snapshot. Structured error if nothing to undo."""
    if not storage.can_undo():
        return {
            "ok": False,
            "error": "Отменять нечего: нет предыдущего состояния.",
            "code": "nothing_to_undo",
        }
    before = storage.get_plan()
    restored = storage.undo_last()
    diff = compute_diff(before, restored, project_start)
    if bus is not None:
        await bus.publish({"version": restored.version, "diff": diff.model_dump(mode="json")})
    return {"ok": True, "plan": _plan_view(restored, project_start)}


async def replace_from_plan(
    storage: Storage, new_tasks_plan: Plan, project_start: date, bus: EventBus | None
) -> dict:
    """Replace the whole plan (Excel import). Snapshots the old plan for undo."""
    current = storage.get_plan()
    replacement = Plan(version=current.version + 1, tasks=new_tasks_plan.tasks)
    diff = compute_diff(current, replacement, project_start)
    storage.commit_plan(replacement)
    if bus is not None:
        await bus.publish({"version": replacement.version, "diff": diff.model_dump(mode="json")})
    return {"ok": True, "plan": _plan_view(replacement, project_start)}


async def reset_demo(storage: Storage, project_start: date, bus: EventBus | None) -> dict:
    plan = storage.reset_to_seed()
    if bus is not None:
        await bus.publish({"version": plan.version, "diff": None})
    return {"ok": True, "plan": _plan_view(plan, project_start)}
