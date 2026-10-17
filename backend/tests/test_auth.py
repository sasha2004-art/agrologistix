import pytest
from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    settings = Settings(
        user_access_pin="123456",
        admin_access_pin="654321",
        sqlite_db_path=":memory:",
    )
    return TestClient(create_app(settings))


def test_verify_pin_returns_dispatcher_role(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/verify-pin",
        headers={"X-Access-Pin": "123456"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "role": "dispatcher",
        "is_admin": False,
        "access_pin_valid": True,
    }


def test_verify_pin_returns_admin_role(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/verify-pin",
        headers={"X-Access-Pin": "654321"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["is_admin"] is True


@pytest.mark.parametrize(
    ("headers", "detail"),
    [
        ({}, "X-Access-Pin header is required"),
        ({"X-Access-Pin": "000000"}, "Invalid access PIN"),
        ({"X-Access-Pin": "12345"}, "Invalid access PIN"),
    ],
)
def test_verify_pin_rejects_invalid_headers(
    client: TestClient,
    headers: dict[str, str],
    detail: str,
) -> None:
    response = client.post("/api/v1/auth/verify-pin", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"code": "unauthorized", "detail": detail}
    assert response.headers["www-authenticate"] == "X-Access-Pin"


def test_failed_pin_attempts_are_throttled(client: TestClient) -> None:
    """A six-digit PIN must not be brute-forced through unlimited guesses."""

    last = None
    for _ in range(12):
        last = client.post(
            "/api/v1/auth/verify-pin",
            headers={"X-Access-Pin": "000000"},
        )
        if last.status_code == 429:
            break

    assert last is not None
    assert last.status_code == 429
    assert last.json()["code"] == "too_many_requests"
    assert int(last.headers["retry-after"]) > 0

    # The block covers a valid PIN too: the source is throttled, not just the code.
    blocked = client.post(
        "/api/v1/auth/verify-pin",
        headers={"X-Access-Pin": "123456"},
    )
    assert blocked.status_code == 429


def test_successful_pin_resets_the_failure_counter(client: TestClient) -> None:
    for _ in range(5):
        client.post("/api/v1/auth/verify-pin", headers={"X-Access-Pin": "000000"})

    assert (
        client.post(
            "/api/v1/auth/verify-pin",
            headers={"X-Access-Pin": "123456"},
        ).status_code
        == 200
    )

    # After a successful login the window starts over, so further guesses answer 401,
    # not an immediate block.
    for _ in range(5):
        assert (
            client.post(
                "/api/v1/auth/verify-pin",
                headers={"X-Access-Pin": "000000"},
            ).status_code
            == 401
        )


def test_session_requires_pin_and_returns_context(client: TestClient) -> None:
    missing_pin = client.get("/api/v1/auth/session")
    authenticated = client.get(
        "/api/v1/auth/session",
        headers={"X-Access-Pin": "123456"},
    )

    assert missing_pin.status_code == 401
    assert missing_pin.json()["code"] == "unauthorized"
    assert authenticated.status_code == 200
    assert authenticated.json()["role"] == "dispatcher"


def test_not_found_uses_api_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"code": "not_found", "detail": "Not Found"}
