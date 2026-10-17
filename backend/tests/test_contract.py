import pytest
from app.schemas import AuthResponse, SolverRequest
from app.schemas.enums import AuthRole, WeatherMode
from pydantic import ValidationError


def test_auth_role_matches_admin_flag() -> None:
    assert AuthResponse(role=AuthRole.ADMIN, is_admin=True).is_admin is True
    assert AuthResponse(role=AuthRole.DISPATCHER, is_admin=False).is_admin is False

    with pytest.raises(ValidationError):
        AuthResponse(role=AuthRole.ADMIN, is_admin=False)


def test_optimize_request_carries_no_scenario_switch() -> None:
    request = SolverRequest()

    assert request.model_dump() == {}


def test_contract_enum_values_are_stable() -> None:
    assert [mode.value for mode in WeatherMode] == [
        "normal",
        "heatwave_35c",
        "heavy_rain",
    ]
