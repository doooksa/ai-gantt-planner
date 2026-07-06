"""Structural validation of a plan.

User-facing messages are in Russian and understandable ("Цикл зависимостей:
Design → Frontend → Design"). Technical detail goes to `detail` for logs.
"""

from __future__ import annotations

from typing import Iterable

from .models import Task


class PlanValidationError(Exception):
    """Raised when a plan is structurally invalid.

    Attributes:
        message: user-facing, Russian, safe to show in the UI.
        code:    stable machine code for the API layer.
        detail:  technical detail for logs (optional).
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "validation_error",
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail


def _names(tasks: Iterable[Task]) -> dict[str, str]:
    return {t.id: t.name for t in tasks}


def validate_structure(tasks: list[Task]) -> None:
    """Validate everything except cycles (cycles are found by the scheduler's
    topological sort so it can report the exact cycle path).

    Raises PlanValidationError on the first problem found.
    """
    ids = [t.id for t in tasks]

    # 1. Unique ids.
    seen: set[str] = set()
    for tid in ids:
        if tid in seen:
            raise PlanValidationError(
                f"Дублирующийся идентификатор задачи: «{tid}».",
                code="duplicate_id",
                detail=f"duplicate task id: {tid}",
            )
        seen.add(tid)

    id_set = set(ids)
    names = _names(tasks)

    for t in tasks:
        # 2. Duration sanity (pydantic already enforces >= 1, but excel/other
        #    entry points may bypass model construction, so keep a guard).
        if t.duration_days < 1:
            raise PlanValidationError(
                f"Длительность задачи «{t.name}» должна быть не меньше 1 дня.",
                code="bad_duration",
                detail=f"task {t.id} duration={t.duration_days}",
            )

        for pid in t.predecessor_ids:
            # 3. Self-dependency.
            if pid == t.id:
                raise PlanValidationError(
                    f"Задача «{t.name}» не может зависеть сама от себя.",
                    code="self_dependency",
                    detail=f"task {t.id} lists itself as predecessor",
                )
            # 4. Predecessor must exist.
            if pid not in id_set:
                raise PlanValidationError(
                    f"Задача «{t.name}» ссылается на несуществующего "
                    f"предшественника «{names.get(pid, pid)}».",
                    code="missing_predecessor",
                    detail=f"task {t.id} -> unknown predecessor {pid}",
                )


def dependents_of(tasks: list[Task], task_id: str) -> list[Task]:
    """Tasks that list `task_id` as a predecessor."""
    return [t for t in tasks if task_id in t.predecessor_ids]
