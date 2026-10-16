import pytest
from app.schemas import AuthResponse, SolverRequest
from app.schemas.enums import AuthRole, SolverMode, WeatherMode
from pydantic import ValidationError


def test_auth_role_matches_admin_flag() -> None:
    assert AuthResponse(role=AuthRole.ADMIN, is_admin=True).is_admin is True
    assert AuthResponse(role=AuthRole.DISPATCHER, is_admin=False).is_admin is False

    with pytest.raises(ValidationError):
        AuthResponse(role=AuthRole.ADMIN, is_admin=False)


def test_what_if_requires_baseline_run() -> None:
    with pytest.raises(ValidationError):
        SolverRequest(mode=SolverMode.WHAT_IF)

    request = SolverRequest(mode=SolverMode.WHAT_IF, baseline_run_id=1)
    assert request.baseline_run_id == 1


def test_contract_enum_values_are_stable() -> None:
    assert [mode.value for mode in WeatherMode] == [
        "normal",
        "heatwave_35c",
        "heavy_rain",
    ]
    assert [mode.value for mode in SolverMode] == ["baseline", "what_if"]
