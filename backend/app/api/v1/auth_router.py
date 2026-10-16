from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.security import AccessContext, authenticate_pin
from app.schemas.auth_schemas import AuthResponse
from app.schemas.error_schemas import APIErrorResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_UNAUTHORIZED_RESPONSE = {"model": APIErrorResponse, "description": "Invalid or missing access PIN"}
SettingsDependency = Annotated[Settings, Depends(get_settings)]
AccessPinHeader = Annotated[str | None, Header(alias="X-Access-Pin")]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "X-Access-Pin"},
    )


@router.post(
    "/verify-pin",
    response_model=AuthResponse,
    responses={status.HTTP_401_UNAUTHORIZED: _UNAUTHORIZED_RESPONSE},
    summary="Verify a six-digit access PIN",
)
def verify_pin(
    settings: SettingsDependency,
    x_access_pin: AccessPinHeader = None,
) -> AuthResponse:
    if x_access_pin is None:
        raise _unauthorized("X-Access-Pin header is required")

    context = authenticate_pin(x_access_pin, settings)
    if context is None:
        raise _unauthorized("Invalid access PIN")
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
