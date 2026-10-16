from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    user_access_pin: SecretStr = Field(default=SecretStr("202601"), repr=False)
    admin_access_pin: SecretStr = Field(default=SecretStr("999999"), repr=False)
    sqlite_db_path: str = "./data/app.db"
    external_api_timeout_sec: float = Field(default=1.5, gt=0.0)
    solver_time_limit_sec: float = Field(default=1.0, gt=0.0)
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

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
