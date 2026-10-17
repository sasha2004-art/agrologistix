import json

from fastapi.testclient import TestClient

AUTH = {"X-Access-Pin": "123456"}
JSON_HEADERS = {**AUTH, "Content-Type": "application/json"}


def post_raw_json(client: TestClient, path: str, payload: str):
    return client.post(path, headers=JSON_HEADERS, content=payload.encode())


def state(client: TestClient) -> dict:
    response = client.get("/api/v1/erp/state", headers=AUTH)
    assert response.status_code == 200
    return response.json()


def test_create_product_appears_in_state(client: TestClient) -> None:
    response = client.post(
        "/api/v1/erp/products",
        headers=AUTH,
        json={
            "code": "blueberry",
            "name": "Голубика садовая",
            "base_spoilage_rate": 0.09,
            "optimal_temp_c": 4.0,
            "base_cost_rub": 420.0,
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["code"] == "blueberry"
    assert created["base_cost_rub"] == 420.0

    products = state(client)["products"]
    assert any(item["id"] == created["id"] for item in products)


def test_create_product_normalizes_code_and_rejects_case_insensitive_duplicate(
    client: TestClient,
) -> None:
    first = client.post(
        "/api/v1/erp/products",
        headers=AUTH,
        json={
            "code": "  BlueBerry  ",
            "name": "  Голубика  ",
            "base_spoilage_rate": 0.09,
            "optimal_temp_c": 4.0,
            "base_cost_rub": 420.0,
        },
    )

    assert first.status_code == 201
    assert first.json()["code"] == "blueberry"
    assert first.json()["name"] == "Голубика"

    duplicate = client.post(
        "/api/v1/erp/products",
        headers=AUTH,
        json={
            "code": "BLUEBERRY",
            "name": "Дубль",
            "base_spoilage_rate": 0.05,
            "optimal_temp_c": 5.0,
            "base_cost_rub": 100.0,
        },
    )

    assert duplicate.status_code == 409


def test_create_product_rejects_non_finite_values_and_blank_fields(client: TestClient) -> None:
    for payload in (
        {
            "code": "inf-cost",
            "name": "Товар",
            "base_spoilage_rate": 0.04,
            "optimal_temp_c": 5.0,
            "base_cost_rub": float("inf"),
        },
        {
            "code": "blank-name",
            "name": "   ",
            "base_spoilage_rate": 0.04,
            "optimal_temp_c": 5.0,
            "base_cost_rub": 10.0,
        },
        {
            "code": "  ",
            "name": "Товар",
            "base_spoilage_rate": 0.04,
            "optimal_temp_c": 5.0,
            "base_cost_rub": 10.0,
        },
    ):
        response = post_raw_json(
            client, "/api/v1/erp/products", json.dumps(payload, allow_nan=True)
        )
        assert response.status_code == 422


def test_create_product_rejects_duplicate_code(client: TestClient) -> None:
    first = state(client)["products"][0]

    response = client.post(
        "/api/v1/erp/products",
        headers=AUTH,
        json={
            "code": first["code"],
            "name": "Дубль",
            "base_spoilage_rate": 0.05,
            "optimal_temp_c": 5.0,
            "base_cost_rub": 100.0,
        },
    )

    assert response.status_code == 409
    assert "уже есть" in response.json()["detail"]


def test_create_client_keeps_dirt_road(client: TestClient) -> None:
    response = client.post(
        "/api/v1/erp/clients",
        headers=AUTH,
        json={
            "name": "Ферма «Заречье»",
            "lat": 54.95,
            "lon": 36.4,
            "road_type": "dirt",
            "address": "Калужская обл., д. Заречье",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["road_type"] == "dirt"
    assert created["address"] == "Калужская обл., д. Заречье"

    clients = state(client)["clients"]
    assert any(item["id"] == created["id"] for item in clients)


def test_create_client_validates_coordinates(client: TestClient) -> None:
    response = client.post(
        "/api/v1/erp/clients",
        headers=AUTH,
        json={"name": "Кривая точка", "lat": 120.0, "lon": 36.4},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_create_client_rejects_non_finite_coordinates_and_blank_names(
    client: TestClient,
) -> None:
    for payload in (
        {"name": "магазин", "lat": float("inf"), "lon": 36.4},
        {"name": "   ", "lat": 54.95, "lon": 36.4},
    ):
        response = post_raw_json(client, "/api/v1/erp/clients", json.dumps(payload, allow_nan=True))
        assert response.status_code == 422


def test_create_truck_appears_in_fleet(client: TestClient) -> None:
    warehouse_id = state(client)["warehouses"][0]["id"]

    response = client.post(
        "/api/v1/erp/trucks",
        headers=AUTH,
        json={
            "name": "ГАЗель Next Тент",
            "plate_number": "е777кх40",
            "warehouse_id": warehouse_id,
            "capacity_kg": 1500.0,
            "cruise_speed_kmh": 70.0,
            "cost_per_km_rub": 22.0,
            "fixed_trip_cost_rub": 900.0,
            "can_use_dirt": True,
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["plate_number"] == "Е777КХ40"
    assert created["can_use_dirt"] is True
    assert created["status"] == "active"


def test_create_truck_rejects_unknown_warehouse(client: TestClient) -> None:
    response = client.post(
        "/api/v1/erp/trucks",
        headers=AUTH,
        json={
            "name": "Потеряшка",
            "plate_number": "А000АА40",
            "warehouse_id": 9999,
            "capacity_kg": 1000.0,
            "cruise_speed_kmh": 60.0,
            "cost_per_km_rub": 20.0,
            "fixed_trip_cost_rub": 500.0,
        },
    )

    assert response.status_code == 404
    assert "Склад" in response.json()["detail"]


def test_create_truck_rejects_non_finite_costs_and_blank_name(client: TestClient) -> None:
    warehouse_id = state(client)["warehouses"][0]["id"]
    payload = {
        "name": "Машина",
        "plate_number": "Е777КХ40",
        "warehouse_id": warehouse_id,
        "capacity_kg": 1500.0,
        "cruise_speed_kmh": 70.0,
        "cost_per_km_rub": float("inf"),
        "fixed_trip_cost_rub": 900.0,
    }
    assert (
        post_raw_json(client, "/api/v1/erp/trucks", json.dumps(payload, allow_nan=True)).status_code
        == 422
    )
    payload["cost_per_km_rub"] = 22.0
    payload["name"] = "   "
    assert client.post("/api/v1/erp/trucks", headers=AUTH, json=payload).status_code == 422


def test_create_truck_rejects_duplicate_plate(client: TestClient) -> None:
    truck = state(client)["trucks"][0]

    response = client.post(
        "/api/v1/erp/trucks",
        headers=AUTH,
        json={
            "name": "Клон",
            "plate_number": truck["plate_number"],
            "warehouse_id": truck["warehouse_id"],
            "capacity_kg": 1000.0,
            "cruise_speed_kmh": 60.0,
            "cost_per_km_rub": 20.0,
            "fixed_trip_cost_rub": 500.0,
        },
    )

    assert response.status_code == 409
    assert "номером" in response.json()["detail"]


def test_create_order_starts_as_planned(client: TestClient) -> None:
    payload_state = state(client)
    client_id = payload_state["clients"][0]["id"]
    product_id = payload_state["products"][0]["id"]

    response = client.post(
        "/api/v1/erp/orders",
        headers=AUTH,
        json={
            "client_id": client_id,
            "product_id": product_id,
            "requested_kg": 750.0,
            "purchase_price_rub": 180.0,
            "unmet_penalty_rub": 40.0,
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["delivery_status"] == "pending"
    assert created["delivered_kg"] == 0.0
    assert created["requested_kg"] == 750.0


def test_create_order_rejects_unknown_client(client: TestClient) -> None:
    product_id = state(client)["products"][0]["id"]

    response = client.post(
        "/api/v1/erp/orders",
        headers=AUTH,
        json={
            "client_id": 9999,
            "product_id": product_id,
            "requested_kg": 100.0,
            "purchase_price_rub": 100.0,
        },
    )

    assert response.status_code == 404
    assert "Покупатель" in response.json()["detail"]


def test_create_stock_batch(client: TestClient) -> None:
    payload_state = state(client)
    warehouse_id = payload_state["warehouses"][0]["id"]

    response = client.post(
        "/api/v1/erp/products",
        headers=AUTH,
        json={
            "code": "radish",
            "name": "Редис",
            "base_spoilage_rate": 0.03,
            "optimal_temp_c": 6.0,
            "base_cost_rub": 90.0,
        },
    )
    product_id = response.json()["id"]

    created = client.post(
        "/api/v1/erp/stocks",
        headers=AUTH,
        json={
            "warehouse_id": warehouse_id,
            "product_id": product_id,
            "available_kg": 1200.0,
            "initial_freshness": 0.88,
        },
    )

    assert created.status_code == 201
    assert created.json()["initial_freshness"] == 0.88

    duplicate = client.post(
        "/api/v1/erp/stocks",
        headers=AUTH,
        json={"warehouse_id": warehouse_id, "product_id": product_id, "available_kg": 10.0},
    )
    assert duplicate.status_code == 409


def test_create_requires_pin(client: TestClient) -> None:
    response = client.post(
        "/api/v1/erp/clients",
        json={"name": "Без ключа", "lat": 55.0, "lon": 36.0},
    )

    assert response.status_code == 401
