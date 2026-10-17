from fastapi.testclient import TestClient

USER_PIN = "123456"
ADMIN_PIN = "654321"
AUTH = {"X-Access-Pin": USER_PIN}
ADMIN_AUTH = {"X-Access-Pin": ADMIN_PIN}


def read_state(client: TestClient) -> dict:
    response = client.get("/api/v1/erp/state", headers=AUTH)
    assert response.status_code == 200
    return response.json()


def test_patch_order_price_is_persisted(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/erp/orders/1",
        headers=AUTH,
        json={"purchase_price_rub": 999.0},
    )

    assert response.status_code == 200
    assert response.json()["purchase_price_rub"] == 999.0

    reloaded = read_state(client)["orders"]
    assert next(order for order in reloaded if order["id"] == 1)["purchase_price_rub"] == 999.0


def test_patch_order_marks_single_order_delivered(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/erp/orders/1",
        headers=AUTH,
        json={"delivery_status": "delivered"},
    )

    assert response.status_code == 200
    assert response.json()["delivery_status"] == "delivered"

    orders = read_state(client)["orders"]
    delivered = [order for order in orders if order["delivery_status"] == "delivered"]
    assert [order["id"] for order in delivered] == [1]


def test_patch_order_with_empty_body_is_rejected(client: TestClient) -> None:
    response = client.patch("/api/v1/erp/orders/1", headers=AUTH, json={})

    assert response.status_code == 400
    assert response.json() == {
        "code": "bad_request",
        "detail": "Укажите хотя бы одно поле для изменения",
    }


def test_patch_order_with_unknown_id_returns_404(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/erp/orders/9999",
        headers=AUTH,
        json={"purchase_price_rub": 100.0},
    )

    assert response.status_code == 404
    assert response.json() == {
        "code": "not_found",
        "detail": "Заказ №9999 не найден",
    }


def test_patch_order_rejects_negative_price_and_unknown_field(client: TestClient) -> None:
    negative = client.patch(
        "/api/v1/erp/orders/1",
        headers=AUTH,
        json={"purchase_price_rub": -5.0},
    )
    unknown = client.patch(
        "/api/v1/erp/orders/1",
        headers=AUTH,
        json={"unexpected_field": 1},
    )

    assert negative.status_code == 422
    assert negative.json()["code"] == "validation_error"
    assert "purchase_price_rub" in negative.json()["fields"]
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "validation_error"


def test_patch_truck_switches_status_both_ways(client: TestClient) -> None:
    broken = client.patch("/api/v1/erp/trucks/1", headers=AUTH, json={"status": "broken"})
    active = client.patch("/api/v1/erp/trucks/1", headers=AUTH, json={"status": "active"})

    assert broken.status_code == 200
    assert broken.json()["status"] == "broken"
    assert active.status_code == 200
    assert active.json()["status"] == "active"


def test_patch_truck_validates_id_and_status(client: TestClient) -> None:
    unknown = client.patch("/api/v1/erp/trucks/9999", headers=AUTH, json={"status": "broken"})
    invalid = client.patch("/api/v1/erp/trucks/1", headers=AUTH, json={"status": "flying"})

    assert unknown.status_code == 404
    assert unknown.json()["code"] == "not_found"
    assert invalid.status_code == 422
    assert "status" in invalid.json()["fields"]


def test_patch_stock_updates_available_weight(client: TestClient) -> None:
    response = client.patch("/api/v1/erp/stocks/1", headers=AUTH, json={"available_kg": 123.0})

    assert response.status_code == 200
    assert response.json()["available_kg"] == 123.0

    stocks = read_state(client)["stocks"]
    assert next(stock for stock in stocks if stock["id"] == 1)["available_kg"] == 123.0


def test_patch_stock_rejects_negative_weight_and_unknown_id(client: TestClient) -> None:
    negative = client.patch("/api/v1/erp/stocks/1", headers=AUTH, json={"available_kg": -1.0})
    unknown = client.patch("/api/v1/erp/stocks/9999", headers=AUTH, json={"available_kg": 1.0})

    assert negative.status_code == 422
    assert "available_kg" in negative.json()["fields"]
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "not_found"


def test_patch_requires_access_pin(client: TestClient) -> None:
    response = client.patch("/api/v1/erp/orders/1", json={"purchase_price_rub": 100.0})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_reset_demo_restores_patched_state(client: TestClient) -> None:
    client.patch("/api/v1/erp/orders/1", headers=AUTH, json={"purchase_price_rub": 999.0})
    client.patch("/api/v1/erp/orders/1", headers=AUTH, json={"delivery_status": "delivered"})
    client.patch("/api/v1/erp/trucks/1", headers=AUTH, json={"status": "broken"})

    reset = client.post("/api/v1/system/reset-demo", headers=ADMIN_AUTH)
    assert reset.status_code == 200

    state = read_state(client)
    order = next(item for item in state["orders"] if item["id"] == 1)
    truck = next(item for item in state["trucks"] if item["id"] == 1)
    assert order["purchase_price_rub"] == 160.0
    assert order["delivery_status"] == "pending"
    assert truck["status"] == "active"
