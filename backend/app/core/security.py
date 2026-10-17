import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.models.erp_models import Account
from app.schemas.auth_schemas import AuthResponse
from app.schemas.enums import AuthRole


@dataclass(frozen=True, slots=True)
class AccessScope:
    role: AuthRole
    is_admin: bool
    account_id: int
    account_name: str

    def to_auth_response(self) -> AuthResponse:
        return AuthResponse(role=self.role, is_admin=self.is_admin)


def authenticate_pin(pin: str, settings: Settings, session: Session) -> AccessScope | None:
    if len(pin) != 6 or not pin.isascii() or not pin.isdigit():
        return None

    if hmac.compare_digest(pin, settings.admin_access_pin.get_secret_value()):
        account = session.exec(select(Account).order_by(Account.id).limit(1)).first()
        account_id = int(account.id or 1) if account is not None else 1
        account_name = account.name if account is not None else "Аккаунт 1"
        return AccessScope(
            role=AuthRole.ADMIN,
            is_admin=True,
            account_id=account_id,
            account_name=account_name,
        )
    if hmac.compare_digest(pin, settings.user_access_pin.get_secret_value()):
        account = session.exec(select(Account).order_by(Account.id).limit(1)).first()
    else:
        account = session.exec(select(Account).where(Account.access_code == pin)).first()
    if account is None:
        return None
    return AccessScope(
        role=AuthRole.DISPATCHER,
        is_admin=False,
        account_id=int(account.id or 1),
        account_name=account.name,
    )


SettingsDependency = Annotated[Settings, Depends(get_settings)]
SessionDependency = Annotated[Session, Depends(get_session)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "X-Access-Pin"},
    )


def get_access_context(
    settings: SettingsDependency,
    session: SessionDependency,
    x_access_pin: Annotated[str | None, Header(alias="X-Access-Pin")] = None,
) -> AccessScope:
    if x_access_pin is None:
        raise _unauthorized("X-Access-Pin header is required")

    context = authenticate_pin(x_access_pin, settings, session)
    if context is None:
        raise _unauthorized("Invalid access PIN")
    return context


def require_admin(
    context: Annotated[AccessScope, Depends(get_access_context)],
) -> AccessScope:
    if not context.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required",
        )
    return context


AccessContext = Annotated[AccessScope, Depends(get_access_context)]
AdminContext = Annotated[AccessScope, Depends(require_admin)]
