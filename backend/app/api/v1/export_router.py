"""XLSX export of a stored solver run."""

from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import AccessContext
from app.schemas.error_schemas import APIErrorResponse
from app.services.xlsx_exporter import XLSX_MEDIA_TYPE, export_run_xlsx, load_export_run

router = APIRouter(prefix="/export", tags=["export"])

SessionDependency = Annotated[Session, Depends(get_session)]

_NOT_FOUND_RESPONSE = {"model": APIErrorResponse, "description": "Solver run was not found"}


def _content_disposition(run_id: int) -> str:
    return f'attachment; filename="agrologistix-run-{run_id}.xlsx"'


@router.get(
    "/run/{run_id}/xlsx",
    response_class=StreamingResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {XLSX_MEDIA_TYPE: {}},
            "description": "Route sheet workbook with a summary sheet and one sheet per route",
        },
        status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
    },
    summary="Download the XLSX route sheet of a baseline or what-if run",
)
def export_run(
    run_id: int,
    _context: AccessContext,
    session: SessionDependency,
) -> StreamingResponse:
    report = load_export_run(session, run_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Solver run with id {run_id} was not found",
        )

    payload = export_run_xlsx(report)
    return StreamingResponse(
        BytesIO(payload),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": _content_disposition(run_id),
            "Content-Length": str(len(payload)),
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
