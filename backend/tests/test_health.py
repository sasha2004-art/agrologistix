from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_endpoint_is_public() -> None:
    response = client.get("/api/v1/health", headers={"X-Access-Pin": "invalid"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
