import logging
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Development PINs that must be rotated before a public deployment.
DEVELOPMENT_PINS = frozenset({"202601", "999999"})


class Settings(BaseSettings):
    app_env: str = "development"
    user_access_pin: SecretStr = Field(default=SecretStr("202601"), repr=False)
    admin_access_pin: SecretStr = Field(default=SecretStr("999999"), repr=False)
    sqlite_db_path: str = "./data/app.db"
    external_api_timeout_sec: float = Field(default=1.5, gt=0.0)
    solver_time_limit_sec: float = Field(default=1.0, gt=0.0)
    # Route consolidation (docs/planning/09-route-consolidation.md): keep the
    # orders of one client on a single truck unless capacity forces a split.
    solver_client_split_penalty_rub: float = Field(default=5000.0, ge=0.0)
    # Realistic trip limits enforced by the solver and the post-check.
    solver_max_stops_per_trip: int = Field(default=5, ge=1, le=50)
    solver_max_trip_hours: float = Field(default=9.0, gt=0.0)
    solver_min_stop_freshness: float = Field(default=0.70, gt=0.0, le=1.0)
    weather_latitude: float = Field(default=55.11, ge=-90.0, le=90.0)
    weather_longitude: float = Field(default=36.61, ge=-180.0, le=180.0)
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
        if user_pin == admin_pin:
            raise ValueError("user and admin access PINs must be different")
        if self.app_env.lower() == "production":
            if not {"user_access_pin", "admin_access_pin"}.issubset(self.model_fields_set):
                raise ValueError("production requires explicit user and admin access PINs")
            if {user_pin, admin_pin} & DEVELOPMENT_PINS:
                logger.warning(
                    "production uses the development access PINs: rotate them for a public demo"
                )
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
