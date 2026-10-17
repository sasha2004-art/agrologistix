import logging
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.accounts import (
    DEVELOPMENT_PINS,
    AccessAccount,
    AccountsMixin,
    build_default_accounts,
    database_path_for,
    parse_accounts,
    validate_accounts,
)

logger = logging.getLogger(__name__)


class Settings(AccountsMixin, BaseSettings):
    app_env: str = "development"
    user_access_pin: SecretStr = Field(default=SecretStr("202601"), repr=False)
    admin_access_pin: SecretStr = Field(default=SecretStr("999999"), repr=False)
    # Optional JSON array that fully replaces the built-in six demo accounts
    # (docs/ARCHITECTURE.md, §4). Empty means the documented default set.
    access_accounts_json: str = ""
    access_accounts: list[AccessAccount] = Field(default_factory=list)
    sqlite_db_path: str = "./data/app.db"
    external_api_timeout_sec: float = Field(default=1.5, gt=0.0)
    # Mapbox строит матрицу по одному запросу на пару точек: 1.5 с хватает погоде,
    # но не дорогам, поэтому у Directions отдельный, более щедрый таймаут.
    mapbox_timeout_sec: float = Field(default=8.0, gt=0.0)
    solver_time_limit_sec: float = Field(default=1.0, gt=0.0)
    # Route consolidation (docs/ARCHITECTURE.md, «Мультистоп и консолидация
    # рейсов»): keep the orders of one client on a single truck unless capacity
    # forces a split.
    solver_client_split_penalty_rub: float = Field(default=5000.0, ge=0.0)
    # Realistic trip limits enforced by the solver and the post-check.
    solver_max_stops_per_trip: int = Field(default=5, ge=1, le=50)
    solver_max_trip_hours: float = Field(default=9.0, gt=0.0)
    solver_min_stop_freshness: float = Field(default=0.70, gt=0.0, le=1.0)
    # Local search over the real route TCO after the MILP draft.
    solver_improve_time_budget_sec: float = Field(default=0.7, gt=0.0)
    solver_improve_max_evaluations: int = Field(default=400, ge=0, le=10_000)
    weather_latitude: float = Field(default=55.11, ge=-90.0, le=90.0)
    weather_longitude: float = Field(default=36.61, ge=-180.0, le=180.0)
    # Brute-force protection for the six-digit PIN: a client is blocked after
    # ``max_attempts`` failures inside the window (see app/core/rate_limit.py).
    auth_rate_limit_max_attempts: int = Field(default=10, ge=1, le=1000)
    auth_rate_limit_window_sec: float = Field(default=60.0, gt=0.0)
    auth_rate_limit_block_sec: float = Field(default=300.0, gt=0.0)
    weather_cache_ttl_sec: int = Field(default=900, gt=0)
    mapbox_secret_token: SecretStr = Field(default=SecretStr(""), repr=False)
    vite_mapbox_public_token: str = ""
    vite_api_base_url: str = "/api/v1"
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:4173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("user_access_pin", "admin_access_pin")
    @classmethod
    def validate_pin(cls, value: SecretStr) -> SecretStr:
        pin = value.get_secret_value()
        if len(pin) != 6 or not pin.isascii() or not pin.isdigit():
            raise ValueError("access PIN must contain exactly six digits")
        return value

    @model_validator(mode="after")
    def validate_access_pins(self) -> "Settings":
        user_pin = self.user_access_pin.get_secret_value()
        admin_pin = self.admin_access_pin.get_secret_value()
        custom_accounts = self.access_accounts_json.strip()
        if user_pin == admin_pin and not custom_accounts:
            raise ValueError("user and admin access PINs must be different")

        accounts = (
            parse_accounts(custom_accounts)
            if custom_accounts
            else build_default_accounts(user_pin, admin_pin)
        )
        self.access_accounts = validate_accounts(accounts)

        if self.app_env.lower() == "production":
            explicit_primary = {"user_access_pin", "admin_access_pin"}.issubset(
                self.model_fields_set
            )
            if not explicit_primary and not custom_accounts:
                raise ValueError("production requires explicit user and admin access PINs")
            if {account.pin_value for account in self.access_accounts} & DEVELOPMENT_PINS:
                logger.warning(
                    "production uses the development access PINs: rotate them for a public demo"
                )
        return self

    def database_path_for(self, account: AccessAccount) -> str:
        """SQLite file of one account: the main file or a per-stand sibling."""

        return database_path_for(self.sqlite_db_path, account)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
