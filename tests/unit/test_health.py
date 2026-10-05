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
        "/api/v1/problems/2/follow",
        json={"user_id": str(uuid4()), "followed_user_id": str(uuid4())},
    )
    assert response.status_code == 501
    assert response.json()["code"] == "todo_tp"


def test_demo_feed_can_be_exercised_without_databases(
    client: TestClient,
) -> None:
    app.dependency_overrides[demo_mode_enabled] = lambda: True
    try:
        response = client.get(f"/api/v1/problems/3/feed/{uuid4()}")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 1
    finally:
        app.dependency_overrides.pop(demo_mode_enabled, None)

