import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings
from app.schemas.auth_schemas import AuthResponse
from app.schemas.enums import AuthRole


def authenticate_pin(pin: str, settings: Settings) -> AuthResponse | None:
    if len(pin) != 6 or not pin.isascii() or not pin.isdigit():
        return None

    if hmac.compare_digest(pin, settings.admin_access_pin.get_secret_value()):
        return AuthResponse(role=AuthRole.ADMIN, is_admin=True)
    if hmac.compare_digest(pin, settings.user_access_pin.get_secret_value()):
        return AuthResponse(role=AuthRole.DISPATCHER, is_admin=False)
    return None


SettingsDependency = Annotated[Settings, Depends(get_settings)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "X-Access-Pin"},
    )


def get_access_context(
    settings: SettingsDependency,
    x_access_pin: Annotated[str | None, Header(alias="X-Access-Pin")] = None,
) -> AuthResponse:
    if x_access_pin is None:
        raise _unauthorized("X-Access-Pin header is required")

    context = authenticate_pin(x_access_pin, settings)
    if context is None:
        raise _unauthorized("Invalid access PIN")
    return context


def require_admin(
    context: Annotated[AuthResponse, Depends(get_access_context)],
) -> AuthResponse:
    if not context.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required",
        )
    return context


AccessContext = Annotated[AuthResponse, Depends(get_access_context)]
AdminContext = Annotated[AuthResponse, Depends(require_admin)]
