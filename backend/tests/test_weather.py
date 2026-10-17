from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
from app.models.run_models import WeatherOverrideState
from app.schemas.enums import WeatherMode
from app.services import weather_service
from app.services.seed_kaluga import seed_database
from app.services.weather_service import (
    WeatherSnapshot,
    read_weather_mode,
    reset_weather_cache,
    write_weather_mode,
)
from fastapi.testclient import TestClient
from sqlmodel import Session

AUTH = {"X-Access-Pin": "123456"}
ADMIN_AUTH = {"X-Access-Pin": "654321"}

LIVE_SNAPSHOT = WeatherSnapshot(
    temperature_c=17.5,
    precipitation_mm=0.5,
    weather_code=2,
    mode=WeatherMode.NORMAL,
    fetched_at=datetime.now(UTC),
)


@pytest.fixture(autouse=True)
def _clean_weather_cache() -> Iterator[None]:
    reset_weather_cache()
    yield
    reset_weather_cache()


def _stub_open_meteo(
    monkeypatch: pytest.MonkeyPatch,
    result: WeatherSnapshot | Exception,
) -> list[int]:
    calls: list[int] = []

    async def fake_fetch(
        settings: object,
        client: httpx.AsyncClient | None = None,
    ) -> WeatherSnapshot:
        calls.append(1)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(weather_service, "fetch_open_meteo", fake_fetch)
    return calls


def test_weather_requires_access_pin(client: TestClient) -> None:
    current = client.get("/api/v1/weather/current")
    override = client.post("/api/v1/weather/override", json={"mode": "heavy_rain"})

    assert current.status_code == 401
    assert override.status_code == 401
    assert current.json()["code"] == "unauthorized"


def test_heatwave_preset_is_returned_by_current(client: TestClient) -> None:
    response = client.post(
        "/api/v1/weather/override",
        headers=AUTH,
        json={"mode": "heatwave_35c"},
    )
    current = client.get("/api/v1/weather/current", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["temperature_c"] == 35.0
    assert response.json()["precipitation_mm"] == 0.0
    assert response.json()["weather_code"] == 0
    assert response.json()["mode"] == "heatwave_35c"
    assert current.json()["temperature_c"] == 35.0
    assert current.json()["mode"] == "heatwave_35c"


def test_heavy_rain_preset_has_precipitation_and_wmo_code(client: TestClient) -> None:
    response = client.post(
        "/api/v1/weather/override",
        headers=AUTH,
        json={"mode": "heavy_rain"},
    )

    assert response.status_code == 200
    assert response.json()["temperature_c"] == 16.0
    assert response.json()["precipitation_mm"] == 12.0
    assert response.json()["weather_code"] == 65


def test_override_rejects_unknown_mode(client: TestClient) -> None:
    response = client.post(
        "/api/v1/weather/override",
        headers=AUTH,
        json={"mode": "snowstorm"},
    )

    assert response.status_code == 422
    assert "mode" in response.json()["fields"]


def test_preset_never_calls_open_meteo(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_open_meteo(monkeypatch, AssertionError("network must not be used"))

    client.post("/api/v1/weather/override", headers=AUTH, json={"mode": "heatwave_35c"})
    current = client.get("/api/v1/weather/current", headers=AUTH)

    assert current.status_code == 200
    assert calls == []


def test_normal_mode_falls_back_offline(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_open_meteo(monkeypatch, httpx.ConnectError("no network"))

    response = client.get("/api/v1/weather/current", headers=AUTH)

    assert response.status_code == 200
    assert response.json()["temperature_c"] == 20.0
    assert response.json()["precipitation_mm"] == 0.0
    assert response.json()["weather_code"] == 1
    assert response.json()["mode"] == "normal"


def test_live_weather_is_cached_for_fifteen_minutes(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_open_meteo(monkeypatch, LIVE_SNAPSHOT)

    first = client.get("/api/v1/weather/current", headers=AUTH)
    second = client.get("/api/v1/weather/current", headers=AUTH)

    assert first.json()["temperature_c"] == 17.5
    assert second.json()["precipitation_mm"] == 0.5
    assert len(calls) == 1


def test_switching_back_to_normal_uses_live_data(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_open_meteo(monkeypatch, LIVE_SNAPSHOT)
    client.post("/api/v1/weather/override", headers=AUTH, json={"mode": "heavy_rain"})

    normal = client.post("/api/v1/weather/override", headers=AUTH, json={"mode": "normal"})

    assert normal.json()["mode"] == "normal"
    assert normal.json()["temperature_c"] == 17.5
    assert len(calls) == 1


def test_preset_survives_in_sqlite(session: Session) -> None:
    seed_database(session)
    assert read_weather_mode(session) is WeatherMode.NORMAL

    write_weather_mode(session, WeatherMode.HEAVY_RAIN)
    state = session.get(WeatherOverrideState, 1)

    assert state is not None
    assert state.mode == "heavy_rain"
    assert read_weather_mode(session) is WeatherMode.HEAVY_RAIN

    write_weather_mode(session, WeatherMode.NORMAL)
    restored = session.get(WeatherOverrideState, 1)
    assert restored is not None
    assert restored.mode == "normal"


def test_reset_demo_resets_weather_preset(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_open_meteo(monkeypatch, LIVE_SNAPSHOT)
    client.post("/api/v1/weather/override", headers=AUTH, json={"mode": "heavy_rain"})

    reset = client.post("/api/v1/system/reset-demo", headers=ADMIN_AUTH)
    current = client.get("/api/v1/weather/current", headers=AUTH)

    assert reset.status_code == 200
    assert current.json()["mode"] == "normal"
    assert current.json()["temperature_c"] == 17.5


def test_read_weather_mode_creates_the_default_row(session: Session) -> None:
    assert session.get(WeatherOverrideState, 1) is None

    mode = read_weather_mode(session)

    state = session.get(WeatherOverrideState, 1)
    assert mode is WeatherMode.NORMAL
    assert state is not None
    assert state.mode == "normal"


def test_write_weather_mode_inserts_a_missing_row(session: Session) -> None:
    write_weather_mode(session, WeatherMode.HEATWAVE_35C)

    state = session.get(WeatherOverrideState, 1)
    assert state is not None
    assert state.mode == "heatwave_35c"


def test_expired_cache_refetches_live_weather(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub_open_meteo(monkeypatch, LIVE_SNAPSHOT)
    clock = {"now": 1_000.0}
    monkeypatch.setattr(weather_service.time, "monotonic", lambda: clock["now"])

    first = client.get("/api/v1/weather/current", headers=AUTH)
    cached = client.get("/api/v1/weather/current", headers=AUTH)
    clock["now"] += 901.0  # TTL is 900 s
    refreshed = client.get("/api/v1/weather/current", headers=AUTH)

    assert len(calls) == 2
    assert first.json()["temperature_c"] == 17.5
    assert cached.json()["temperature_c"] == 17.5
    assert refreshed.json()["temperature_c"] == 17.5
