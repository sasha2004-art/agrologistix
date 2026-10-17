"""Access accounts: every demo stand logs in with its own PIN.

An account is a named login with a six-digit PIN, a role and a *data profile*.
Data isolation is done at the storage layer: the primary account keeps the main
SQLite file (``SQLITE_DB_PATH``), while every other stand gets its own database
file next to it (``<stem>-<account_id>.db``) seeded from its own profile. That
way the ERP, solver runs and route cache of one stand never leak into another,
and the existing query layer stays untouched (docs/ARCHITECTURE.md, §4–§5).
"""

from __future__ import annotations

import hmac
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.schemas.enums import AuthRole

# The stand that owns ``SQLITE_DB_PATH``: it keeps the documented base dataset.
PRIMARY_ACCOUNT_ID = "dispatcher-1"
# The administrator shares the primary dataset with dispatcher-1, so the admin
# console (demo reset) always shows the same stand as the default login.
ADMIN_ACCOUNT_ID = "admin"

PIN_LENGTH = 6


def _validate_pin(value: SecretStr) -> SecretStr:
    pin = value.get_secret_value()
    if len(pin) != PIN_LENGTH or not pin.isascii() or not pin.isdigit():
        raise ValueError("access PIN must contain exactly six digits")
    return value


class AccessAccount(BaseModel):
    """One login of the demo service with its own isolated dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=2, max_length=40)
    login: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=80)
    role: AuthRole
    pin: SecretStr = Field(repr=False)
    profile: str = Field(default="base", min_length=2, max_length=40)
    # True for the accounts that live in the main SQLite file.
    shares_primary_db: bool = False

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: SecretStr) -> SecretStr:
        return _validate_pin(value)

    @property
    def pin_value(self) -> str:
        return self.pin.get_secret_value()

    @property
    def is_admin(self) -> bool:
        return self.role is AuthRole.ADMIN

    def matches_pin(self, candidate: str) -> bool:
        return hmac.compare_digest(candidate, self.pin_value)

    def __repr__(self) -> str:  # pragma: no cover - never leak the PIN
        return f"AccessAccount(id={self.id!r}, login={self.login!r}, role={self.role.value!r})"


# Stands behind dispatcher-1: each one is seeded from its own data profile.
STAND_ACCOUNT_SEED: tuple[dict[str, str], ...] = (
    {
        "id": "dispatcher-2",
        "login": "dispatcher2",
        "name": "Логист смены №2",
        "role": AuthRole.DISPATCHER.value,
        "pin": "582613",
        "profile": "peak",
    },
    {
        "id": "dispatcher-3",
        "login": "dispatcher3",
        "name": "Логист смены №3",
        "role": AuthRole.DISPATCHER.value,
        "pin": "740158",
        "profile": "heat",
    },
    {
        "id": "dispatcher-4",
        "login": "dispatcher4",
        "name": "Логист смены №4",
        "role": AuthRole.DISPATCHER.value,
        "pin": "296340",
        "profile": "rain",
    },
    {
        "id": "dispatcher-5",
        "login": "dispatcher5",
        "name": "Логист смены №5",
        "role": AuthRole.DISPATCHER.value,
        "pin": "861972",
        "profile": "scarce",
    },
    {
        "id": "dispatcher-6",
        "login": "dispatcher6",
        "name": "Логист смены №6",
        "role": AuthRole.DISPATCHER.value,
        "pin": "112233",
        "profile": "base",
    },
    {
        "id": "dispatcher-7",
        "login": "dispatcher7",
        "name": "Логист смены №7",
        "role": AuthRole.DISPATCHER.value,
        "pin": "445566",
        "profile": "peak",
    },
    {
        "id": "dispatcher-8",
        "login": "dispatcher8",
        "name": "Логист смены №8",
        "role": AuthRole.DISPATCHER.value,
        "pin": "778899",
        "profile": "heat",
    },
    {
        "id": "dispatcher-9",
        "login": "dispatcher9",
        "name": "Логист смены №9",
        "role": AuthRole.DISPATCHER.value,
        "pin": "334455",
        "profile": "rain",
    },
    {
        "id": "dispatcher-10",
        "login": "dispatcher10",
        "name": "Логист смены №10",
        "role": AuthRole.DISPATCHER.value,
        "pin": "667788",
        "profile": "scarce",
    },
    {
        "id": "dispatcher-11",
        "login": "dispatcher11",
        "name": "Логист смены №11",
        "role": AuthRole.DISPATCHER.value,
        "pin": "990011",
        "profile": "base",
    },
)

# PINs that must be rotated before a public deployment.
DEVELOPMENT_PINS = frozenset(
    {"202601", "999999"} | {str(item["pin"]) for item in STAND_ACCOUNT_SEED}
)


def build_default_accounts(user_pin: str, admin_pin: str) -> list[AccessAccount]:
    """Six demo accounts: five dispatchers and one administrator.

    ``USER_ACCESS_PIN`` keeps owning the primary dataset, ``ADMIN_ACCESS_PIN``
    shares it, and the four extra stands are seeded from their own profiles.
    """

    primary = AccessAccount(
        id=PRIMARY_ACCOUNT_ID,
        login="dispatcher1",
        name="Логист смены №1",
        role=AuthRole.DISPATCHER,
        pin=SecretStr(user_pin),
        profile="base",
        shares_primary_db=True,
    )
    admin = AccessAccount(
        id=ADMIN_ACCOUNT_ID,
        login="admin",
        name="Администратор демо",
        role=AuthRole.ADMIN,
        pin=SecretStr(admin_pin),
        profile="base",
        shares_primary_db=True,
    )
    stands = [AccessAccount.model_validate(item) for item in STAND_ACCOUNT_SEED]
    return [primary, *stands, admin]


def parse_accounts(raw_json: str) -> list[AccessAccount]:
    """Parse the ``ACCESS_ACCOUNTS`` JSON array of account objects."""

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as error:
        raise ValueError(f"ACCESS_ACCOUNTS is not valid JSON: {error}") from error
    if not isinstance(payload, list) or not payload:
        raise ValueError("ACCESS_ACCOUNTS must be a non-empty JSON array")
    return [AccessAccount.model_validate(item) for item in payload]


def ensure_unique_accounts(accounts: list[AccessAccount]) -> None:
    """Reject duplicated identifiers, logins and PINs."""

    for field_name, values in (
        ("id", [account.id for account in accounts]),
        ("login", [account.login for account in accounts]),
        ("pin", [account.pin_value for account in accounts]),
    ):
        if len(set(values)) != len(values):
            raise ValueError(f"access accounts must have unique {field_name} values")


def ensure_primary_account(accounts: list[AccessAccount]) -> list[AccessAccount]:
    """Guarantee that exactly one account owns the main database file."""

    if any(account.shares_primary_db for account in accounts):
        return accounts
    first = accounts[0]
    promoted = first.model_copy(update={"shares_primary_db": True})
    return [promoted, *accounts[1:]]


def database_path_for(sqlite_db_path: str, account: AccessAccount) -> str:
    """SQLite file of one stand: the main path for the primary account."""

    if account.shares_primary_db or sqlite_db_path == ":memory:":
        return sqlite_db_path
    path = Path(sqlite_db_path)
    return str(path.with_name(f"{path.stem}-{account.id}{path.suffix or '.db'}"))


class AccountsMixin:
    """Account lookup helpers shared by :class:`Settings`.

    Declared as a mixin so ``Settings`` stays a thin configuration object and
    the lookup logic can be unit-tested on its own.
    """

    # Populated by ``Settings``; the annotation lives there, not on the mixin.
    access_accounts: list[AccessAccount]

    def account_by_id(self, account_id: str) -> AccessAccount | None:
        return next((item for item in self.access_accounts if item.id == account_id), None)

    def account_by_pin(self, pin: str) -> AccessAccount | None:
        return next((item for item in self.access_accounts if item.matches_pin(pin)), None)

    @property
    def primary_account(self) -> AccessAccount:
        return next(
            (item for item in self.access_accounts if item.shares_primary_db),
            self.access_accounts[0],
        )


def validate_accounts(accounts: list[AccessAccount]) -> list[AccessAccount]:
    """Full account-list validation used by ``Settings``."""

    resolved = ensure_primary_account(accounts)
    ensure_unique_accounts(resolved)
    return resolved


__all__ = [
    "ADMIN_ACCOUNT_ID",
    "DEVELOPMENT_PINS",
    "PRIMARY_ACCOUNT_ID",
    "STAND_ACCOUNT_SEED",
    "AccessAccount",
    "AccountsMixin",
    "build_default_accounts",
    "database_path_for",
    "ensure_unique_accounts",
    "parse_accounts",
    "validate_accounts",
]