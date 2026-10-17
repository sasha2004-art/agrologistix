import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_settings_expose_comma_separated_cors_origins() -> None:
    settings = Settings(cors_allowed_origins=" http://one.test, http://two.test ")

    assert settings.cors_origins == ["http://one.test", "http://two.test"]


@pytest.mark.parametrize(
    "pin", ["12345", "1234567", "\uff11\uff12\uff13\uff14\uff15\uff16", "abcdef"]
)
def test_settings_reject_invalid_access_pin(pin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(user_access_pin=pin)


def test_settings_reject_identical_user_and_admin_pins() -> None:
    with pytest.raises(ValidationError, match="must be different"):
        Settings(user_access_pin="123456", admin_access_pin="123456")


def test_production_requires_explicit_non_default_pins() -> None:
    with pytest.raises(ValidationError, match="requires explicit"):
        Settings(app_env="production")

    with pytest.raises(ValidationError, match="development defaults"):
        Settings(
            app_env="production",
            user_access_pin="123456",
            admin_access_pin="999999",
        )


def test_production_accepts_explicit_distinct_pins() -> None:
    settings = Settings(
        app_env="production",
        user_access_pin="123456",
        admin_access_pin="654321",
    )

    assert settings.app_env == "production"
