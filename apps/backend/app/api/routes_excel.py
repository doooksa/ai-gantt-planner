"""Excel import/export endpoints."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from .. import services
from ..deps import get_project_start, get_storage
from ..events import get_event_bus
from ..excel import export_excel, parse_excel
from ..domain.validators import PlanValidationError

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB
_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/upload-excel")
async def upload_excel(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 2 МБ.")
    try:
        parsed = parse_excel(data)
    except PlanValidationError as exc:
        # User-facing Russian message; technical detail stays in logs.
        raise HTTPException(status_code=400, detail=exc.message) from exc

    return await services.replace_from_plan(
        get_storage(), parsed, get_project_start(), get_event_bus()
    )


@router.get("/export-excel")
async def export_excel_endpoint() -> Response:
    plan = get_storage().get_plan()
    data = export_excel(plan, get_project_start())
    return Response(
        content=data,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="plan.xlsx"'},
    )
