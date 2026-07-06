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

# Documented so the LLM knows the exact shape of each op's opaque `payload` dict.
_OPS_CATALOG = """
Патч — это {"ops": [ ... ]}. Каждая операция: {"type", "selector"?, "payload"}.
Селектор указывает НА КАКИЕ задачи действовать: {"by_id": "..."} | {"by_name": "..."} | {"by_assignee": "..."}.

Типы операций и их payload:
- add_task        (без селектора) payload: {"name", "duration_days", "description"?, "assignee"?, "predecessors"?: [имена или id], "offset_days"?}
- update_task     (селектор) payload: любые из {"name", "description", "assignee", "duration_days", "offset_days"}
- delete_task     (селектор) payload: {} — зависимые задачи теряют эту зависимость (вернётся предупреждение)
- shift_task      (селектор) payload: {"days": N} — сдвиг: N>0 позже, N<0 раньше (не раньше самой ранней возможной даты)
- reassign        (селектор) payload: {"assignee": "Имя"} — для массовой правки используй селектор by_assignee ОДНИМ патчем
- set_dependencies(селектор) payload: {"predecessors": [имена или id]} — ПОЛНОСТЬЮ заменяет список предшественников ([] убирает все)

Примеры:
- «перенеси Frontend на 3 дня позже» → {"ops":[{"type":"shift_task","selector":{"by_name":"Frontend"},"payload":{"days":3}}]}
- «все задачи Ivan → Maria»          → {"ops":[{"type":"reassign","selector":{"by_assignee":"Ivan"},"payload":{"assignee":"Maria"}}]}
- «Demo зависит ещё и от Excel Export»→ сначала get_plan, затем set_dependencies с ПОЛНЫМ списком (старые + Excel Export)
"""


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_plan() -> dict:
        """Вернуть текущий план проекта с вычисленными датами начала и конца
        каждой задачи. Всегда вызывай это перед внесением правок."""
        return services.get_plan_view(get_storage(), get_project_start())

    @mcp.tool(
        description="Сухой прогон патча: вернуть diff (before/after) и ошибки "
        "БЕЗ применения. Используй перед apply_patch, чтобы проверить правки.\n"
        + _OPS_CATALOG
    )
    def validate_patch(patch: Patch) -> dict:
        return services.validate(get_storage(), patch, get_project_start())

    @mcp.tool(
        description="Атомарно применить патч, пересчитать расписание и вернуть "
        "diff. Если хотя бы одна операция невалидна — весь патч откатывается и "
        "возвращается ошибка {ok:false, error}. Массовые правки делай ОДНИМ "
        "патчем с селектором (например, by_assignee), а не несколькими вызовами.\n"
        + _OPS_CATALOG
    )
    async def apply_patch(patch: Patch) -> dict:
        return await services.apply(
            get_storage(), patch, get_project_start(), get_event_bus()
        )

    @mcp.tool()
    async def undo_last() -> dict:
        """Откатить план к предыдущему снапшоту (отменить последнее изменение)."""
        return await services.undo(get_storage(), get_project_start(), get_event_bus())
