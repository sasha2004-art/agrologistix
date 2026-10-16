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
