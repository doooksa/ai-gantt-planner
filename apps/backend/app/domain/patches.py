"""Apply a Patch (list of ops with selectors) to a Plan, atomically.

Contract:
    * `apply_patch` never mutates the input plan.
    * All ops are applied to a working copy; the result is then validated +
      scheduled. If ANY op or the final validation fails, PlanValidationError is
      raised and the caller keeps the original plan (atomic rollback).
    * Mass edits ("all of Ivan's tasks -> Maria") are a single op with a
      `by_assignee` selector, not N ops.
"""

from __future__ import annotations

from datetime import date

from .models import Diff, Op, Patch, Plan, ScheduledTask, Selector, Task, TaskDiff
from .scheduler import schedule
from .slug import unique_slug
from .validators import PlanValidationError, dependents_of


# --- selector / reference resolution -------------------------------------


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _match(tasks: list[Task], selector: Selector | None) -> list[Task]:
    if selector is None:
        return []
    if selector.by_id is not None:
        return [t for t in tasks if t.id == selector.by_id]
    if selector.by_name is not None:
        target = _norm(selector.by_name)
        return [t for t in tasks if _norm(t.name) == target]
    if selector.by_assignee is not None:
        target = _norm(selector.by_assignee)
        return [t for t in tasks if t.assignee and _norm(t.assignee) == target]
    return []


def _resolve_ref(tasks: list[Task], ref: str) -> str:
    """Resolve a task reference (id or name) to an id; raise if unknown."""
    for t in tasks:
        if t.id == ref:
            return t.id
    target = _norm(ref)
    for t in tasks:
        if _norm(t.name) == target:
            return t.id
    raise PlanValidationError(
        f"Неизвестная задача-предшественник: «{ref}».",
        code="missing_predecessor",
        detail=f"unresolved predecessor ref: {ref}",
    )


def _resolve_pred_ids(tasks: list[Task], refs: list) -> list[str]:
    return [_resolve_ref(tasks, str(r)) for r in refs]


def _require_match(matched: list[Task], op: Op) -> None:
    if not matched:
        raise PlanValidationError(
            "Не найдено ни одной задачи по заданному условию.",
            code="selector_no_match",
            detail=f"op {op.type} selector matched nothing: {op.selector}",
        )


# --- individual operations (mutate the working list in place) ------------


def _op_add_task(tasks: list[Task], op: Op, warnings: list[str]) -> None:
    p = op.payload
    name = p.get("name")
    if not name:
        raise PlanValidationError(
            "Для добавления задачи требуется название.",
            code="missing_field",
            detail="add_task without name",
        )
    if "duration_days" not in p:
        raise PlanValidationError(
            f"Для задачи «{name}» требуется длительность.",
            code="missing_field",
            detail="add_task without duration_days",
        )
    existing_ids = {t.id for t in tasks}
    task_id = p.get("id") or unique_slug(name, existing_ids)
    pred_refs = p.get("predecessor_ids") or p.get("predecessors") or []
    predecessor_ids = _resolve_pred_ids(tasks, list(pred_refs))
    tasks.append(
        Task(
            id=task_id,
            name=name,
            description=p.get("description"),
            assignee=p.get("assignee"),
            duration_days=int(p["duration_days"]),
            predecessor_ids=predecessor_ids,
            offset_days=int(p.get("offset_days", 0)),
        )
    )


def _op_update_task(tasks: list[Task], op: Op, warnings: list[str]) -> None:
    matched = _match(tasks, op.selector)
    _require_match(matched, op)
    p = op.payload
    for t in matched:
        if "name" in p:
            t.name = p["name"]
        if "description" in p:
            t.description = p["description"]
        if "assignee" in p:
            t.assignee = p["assignee"]
        if "duration_days" in p:
            t.duration_days = int(p["duration_days"])
        if "offset_days" in p:
            t.offset_days = int(p["offset_days"])


def _op_delete_task(tasks: list[Task], op: Op, warnings: list[str]) -> None:
    matched = _match(tasks, op.selector)
    _require_match(matched, op)
    for target in matched:
        deps = [d.name for d in dependents_of(tasks, target.id) if d.id != target.id]
        if deps:
            warnings.append(
                f"Задача «{target.name}» удалена; зависимость на неё убрана у: "
                + ", ".join(deps)
                + "."
            )
    remove_ids = {t.id for t in matched}
    tasks[:] = [t for t in tasks if t.id not in remove_ids]
    # Strip dangling references so the plan stays valid.
    for t in tasks:
        t.predecessor_ids = [p for p in t.predecessor_ids if p not in remove_ids]


def _op_shift_task(tasks: list[Task], op: Op, warnings: list[str]) -> None:
    matched = _match(tasks, op.selector)
    _require_match(matched, op)
    days = int(op.payload.get("days", 0))
    for t in matched:
        # offset_days is clamped at 0 (can't push a task before its earliest date).
        t.offset_days = max(0, t.offset_days + days)


def _op_reassign(tasks: list[Task], op: Op, warnings: list[str]) -> None:
    matched = _match(tasks, op.selector)
    _require_match(matched, op)
    to = op.payload.get("assignee") or op.payload.get("to")
    if not to:
        raise PlanValidationError(
            "Не указан новый исполнитель.",
            code="missing_field",
            detail="reassign without target assignee",
        )
    for t in matched:
        t.assignee = to


def _op_set_dependencies(tasks: list[Task], op: Op, warnings: list[str]) -> None:
    matched = _match(tasks, op.selector)
    _require_match(matched, op)
    refs = op.payload.get("predecessor_ids", op.payload.get("predecessors", []))
    new_pred_ids = _resolve_pred_ids(tasks, list(refs))
    for t in matched:
        t.predecessor_ids = [p for p in new_pred_ids if p != t.id]


_DISPATCH = {
    "add_task": _op_add_task,
    "update_task": _op_update_task,
    "delete_task": _op_delete_task,
    "shift_task": _op_shift_task,
    "reassign": _op_reassign,
    "set_dependencies": _op_set_dependencies,
}


# --- diff -----------------------------------------------------------------


def compute_diff(
    before: Plan, after: Plan, project_start: date | None = None
) -> Diff:
    """Schedule both plans and diff them task-by-task (dates included)."""
    before_sched = {t.id: t for t in schedule(before.tasks, project_start)} if before.tasks else {}
    after_sched = {t.id: t for t in schedule(after.tasks, project_start)} if after.tasks else {}

    diffs: list[TaskDiff] = []
    for tid, after_t in after_sched.items():
        before_t = before_sched.get(tid)
        if before_t is None:
            diffs.append(TaskDiff(id=tid, change="added", after=after_t))
        elif before_t != after_t:
            diffs.append(TaskDiff(id=tid, change="updated", before=before_t, after=after_t))
    for tid, before_t in before_sched.items():
        if tid not in after_sched:
            diffs.append(TaskDiff(id=tid, change="removed", before=before_t))

    return Diff(
        version_before=before.version,
        version_after=after.version,
        tasks=diffs,
    )


# --- public entry point ---------------------------------------------------


def apply_patch(
    plan: Plan, patch: Patch, project_start: date | None = None
) -> tuple[Plan, Diff]:
    """Apply `patch` to `plan`, returning (new_plan, diff).

    Atomic: on any failure raises PlanValidationError and `plan` is untouched.
    Bumps `version` by 1 on success.
    """
    working = [t.model_copy(deep=True) for t in plan.tasks]
    warnings: list[str] = []

    for op in patch.ops:
        handler = _DISPATCH.get(op.type)
        if handler is None:  # pragma: no cover - guarded by the Op Literal type
            raise PlanValidationError(
                f"Неизвестная операция: «{op.type}».",
                code="unknown_op",
                detail=f"unknown op type {op.type}",
            )
        handler(working, op, warnings)

    # Validate + schedule the result (raises -> caller keeps original plan).
    schedule(working, project_start)

    new_plan = Plan(version=plan.version + 1, tasks=working)
    diff = compute_diff(plan, new_plan, project_start)
    diff.warnings = warnings
    return new_plan, diff
