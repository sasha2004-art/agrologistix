from fastapi.testclient import TestClient

USER_PIN = "123456"
ADMIN_PIN = "654321"
DISALLOWED_PIN = "000000"


def test_erp_state_requires_pin(client: TestClient) -> None:
    response = client.get("/api/v1/erp/state")

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_erp_state_returns_full_demo_dataset(client: TestClient) -> None:
    response = client.get("/api/v1/erp/state", headers={"X-Access-Pin": USER_PIN})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["warehouses"]) == 2
    assert len(payload["products"]) == 3
    assert len(payload["stocks"]) == 6
    assert len(payload["clients"]) == 5
    assert len(payload["orders"]) == 9
    assert len(payload["trucks"]) == 3
    assert {client["road_type"] for client in payload["clients"]} == {"asphalt", "dirt"}
    assert payload["products"][0]["code"] == "strawberry"


def test_reset_demo_is_forbidden_for_dispatcher(client: TestClient) -> None:
    response = client.post(
        "/api/v1/system/reset-demo",
        headers={"X-Access-Pin": USER_PIN},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_reset_demo_is_forbidden_for_invalid_pin(client: TestClient) -> None:
    response = client.post(
        "/api/v1/system/reset-demo",
        headers={"X-Access-Pin": DISALLOWED_PIN},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_reset_demo_rebuilds_admin_dataset(client: TestClient) -> None:
    headers = {"X-Access-Pin": ADMIN_PIN}
    response = client.post("/api/v1/system/reset-demo", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "status": "ok",
        "warehouses": 2,
        "products": 3,
        "stocks": 6,
        "clients": 5,
        "orders": 9,
        "trucks": 3,
        "seeded": True,
    }

    state = client.get("/api/v1/erp/state", headers=headers).json()
    assert len(state["orders"]) == payload["orders"]
