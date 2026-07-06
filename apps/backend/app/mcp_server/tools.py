"""The four MCP tools (exactly these, per spec) registered on a FastMCP server.

Thin wrappers over `app.services`; they resolve the shared Storage / event bus /
project-start at call time so the same singletons are used everywhere.

    get_plan()               -> current plan with computed dates
    validate_patch(patch)    -> dry-run diff + errors, NOT applied
    apply_patch(patch)       -> apply atomically, recompute, broadcast, diff
    undo_last()              -> revert to the previous snapshot
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .. import services
from ..deps import get_project_start, get_storage
from ..domain.models import Patch
from ..events import get_event_bus


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_plan() -> dict:
        """Вернуть текущий план проекта с вычисленными датами начала и конца
        каждой задачи. Всегда вызывай это перед внесением правок."""
        return services.get_plan_view(get_storage(), get_project_start())

    @mcp.tool()
    def validate_patch(patch: Patch) -> dict:
        """Сухой прогон патча: вернуть diff (before/after) и ошибки БЕЗ
        применения. Используй перед apply_patch, чтобы проверить правки."""
        return services.validate(get_storage(), patch, get_project_start())

    @mcp.tool()
    async def apply_patch(patch: Patch) -> dict:
        """Атомарно применить патч, пересчитать расписание и вернуть diff. Если
        хотя бы одна операция невалидна — весь патч откатывается и возвращается
        ошибка. Массовые правки делай ОДНИМ патчем с селектором (например,
        by_assignee), а не несколькими вызовами."""
        return await services.apply(
            get_storage(), patch, get_project_start(), get_event_bus()
        )

    @mcp.tool()
    async def undo_last() -> dict:
        """Откатить план к предыдущему снапшоту (отменить последнее изменение)."""
        return await services.undo(get_storage(), get_project_start(), get_event_bus())
