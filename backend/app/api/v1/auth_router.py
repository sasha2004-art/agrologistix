from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.core.config import Settings, get_settings
from app.core.rate_limit import LIMITER, client_key
from app.core.security import AccessContext, authenticate_pin
from app.schemas.auth_schemas import AuthResponse
from app.schemas.error_schemas import APIErrorResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_UNAUTHORIZED_RESPONSE = {"model": APIErrorResponse, "description": "Invalid or missing access PIN"}
_TOO_MANY_RESPONSE = {"model": APIErrorResponse, "description": "Too many failed PIN attempts"}
SettingsDependency = Annotated[Settings, Depends(get_settings)]
AccessPinHeader = Annotated[str | None, Header(alias="X-Access-Pin")]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "X-Access-Pin"},
    )


def _too_many(retry_after: float) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many failed PIN attempts, try again later",
        headers={"Retry-After": str(max(1, int(retry_after + 0.999)))},
    )


@router.post(
    "/verify-pin",
    response_model=AuthResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED_RESPONSE,
        status.HTTP_429_TOO_MANY_REQUESTS: _TOO_MANY_RESPONSE,
    },
    summary="Verify a six-digit access PIN",
)
def verify_pin(
    request: Request,
    settings: SettingsDependency,
    x_access_pin: AccessPinHeader = None,
) -> AuthResponse:
    key = client_key(request)
    retry_after = LIMITER.retry_after(key, settings)
    if retry_after > 0.0:
        # A six-digit PIN is brute-forceable, so failed guesses are throttled.
        raise _too_many(retry_after)

    if x_access_pin is None:
        raise _unauthorized("X-Access-Pin header is required")

    context = authenticate_pin(x_access_pin, settings)
    if context is None:
        LIMITER.register_failure(key, settings)
        raise _unauthorized("Invalid access PIN")
    LIMITER.reset(key)
    return context


@router.get(
    "/session",
    response_model=AuthResponse,
    responses={
        status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED_RESPONSE,
    },
    summary="Read the current authenticated session",
)
def read_session(context: AccessContext) -> AuthResponse:
    return context
