"""Plan REST endpoints: read, undo, reset, health."""

from __future__ import annotations

from fastapi import APIRouter

from .. import services
from ..deps import get_project_start, get_storage
from ..events import get_event_bus

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/plan")
async def get_plan() -> dict:
    return services.get_plan_view(get_storage(), get_project_start())


@router.post("/undo")
async def undo() -> dict:
    return await services.undo(get_storage(), get_project_start(), get_event_bus())


@router.post("/reset-demo")
async def reset_demo() -> dict:
    return await services.reset_demo(get_storage(), get_project_start(), get_event_bus())
