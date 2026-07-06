"""Deterministic scheduler. No LLM, no randomness.

Algorithm (per spec):
    1. Validate predecessors exist (delegated to validators.validate_structure).
    2. Detect cycles via topological sort; a cycle -> PlanValidationError that
       names the tasks in the cycle.
    3. Forward pass on calendar days:
         - no predecessors      -> start = project_start
         - otherwise            -> start = max(end of predecessors) + 1 day
         - end = start + duration_days - 1
       plus an optional per-task `offset_days` lag added to the computed start.
    4. Working days vs calendar days: calendar days now; working-day support is
       an explicit Roadmap item.
"""

from __future__ import annotations

from datetime import date, timedelta

from .models import ScheduledTask, Task
from .validators import PlanValidationError, validate_structure


def _topological_order(tasks: list[Task]) -> list[Task]:
    """Return tasks in dependency order (predecessors first).

    Raises PlanValidationError naming the cycle if the graph is cyclic.
    """
    by_id = {t.id: t for t in tasks}

    # DFS with coloring: 0=unvisited, 1=on-stack, 2=done.
    color: dict[str, int] = {t.id: 0 for t in tasks}
    order: list[Task] = []
    stack_path: list[str] = []

    def visit(tid: str) -> None:
        color[tid] = 1
        stack_path.append(tid)
        for pid in by_id[tid].predecessor_ids:
            if color[pid] == 1:
                # Found a back edge -> extract the cycle path for the message.
                cycle_ids = stack_path[stack_path.index(pid):] + [pid]
                cycle_names = " → ".join(by_id[c].name for c in cycle_ids)
                raise PlanValidationError(
                    f"Цикл зависимостей: {cycle_names}.",
                    code="cycle",
                    detail=f"cycle: {' -> '.join(cycle_ids)}",
                )
            if color[pid] == 0:
                visit(pid)
        stack_path.pop()
        color[tid] = 2
        order.append(by_id[tid])

    for t in tasks:
        if color[t.id] == 0:
            visit(t.id)
    return order


def schedule(tasks: list[Task], project_start: date | None = None) -> list[ScheduledTask]:
    """Validate + compute start/end for every task.

    Returns ScheduledTask list in the SAME order as the input `tasks`.
    `project_start` defaults to today (calendar date).
    """
    if project_start is None:
        project_start = date.today()

    validate_structure(tasks)
    ordered = _topological_order(tasks)

    computed: dict[str, ScheduledTask] = {}
    for t in ordered:
        if t.predecessor_ids:
            base_start = max(computed[p].end for p in t.predecessor_ids) + timedelta(days=1)
        else:
            base_start = project_start
        start = base_start + timedelta(days=t.offset_days)
        end = start + timedelta(days=t.duration_days - 1)
        computed[t.id] = ScheduledTask(**t.model_dump(), start=start, end=end)

    # Preserve caller's original ordering.
    return [computed[t.id] for t in tasks]
