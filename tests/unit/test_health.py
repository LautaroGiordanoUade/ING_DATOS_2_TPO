from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies.demo import demo_mode_enabled
from app.main import app


def test_liveness_does_not_require_databases(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_pending_endpoint_returns_controlled_501(client: TestClient) -> None:
    response = client.post(
        "/api/v1/problems/6/message",
        json={"conversation_id": str(uuid4()), "sender_id": str(uuid4()), "text": "pending"},
    )
    assert response.status_code == 501
    assert response.json()["code"] == "todo_tp"


def test_unrelated_demo_messages_remain_available(
    client: TestClient,
) -> None:
    app.dependency_overrides[demo_mode_enabled] = lambda: True
    try:
        response = client.post(
            "/api/v1/problems/6/message",
            json={"conversation_id": str(uuid4()), "sender_id": str(uuid4()), "text": "demo"},
        )
        assert response.status_code == 202
    finally:
        app.dependency_overrides.pop(demo_mode_enabled, None)
