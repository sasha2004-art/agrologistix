from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def _error_code(status_code: int) -> str:
    return {
        status.HTTP_401_UNAUTHORIZED: "unauthorized",
        status.HTTP_403_FORBIDDEN: "forbidden",
        status.HTTP_404_NOT_FOUND: "not_found",
    }.get(status_code, "request_error")


async def http_exception_handler(
    _request: Request,
    exception: StarletteHTTPException,
) -> JSONResponse:
    detail = exception.detail if isinstance(exception.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exception.status_code,
        content={"code": _error_code(exception.status_code), "detail": detail},
        headers=exception.headers,
    )


async def validation_exception_handler(
    _request: Request,
    exception: RequestValidationError,
) -> JSONResponse:
    fields: dict[str, list[str]] = {}
    for error in exception.errors():
        location = ".".join(str(item) for item in error["loc"] if item != "body") or "body"
        fields.setdefault(location, []).append(str(error["msg"]))

    content: dict[str, Any] = {
        "code": "validation_error",
        "detail": "Request validation failed",
        "fields": fields,
    }
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=content)
