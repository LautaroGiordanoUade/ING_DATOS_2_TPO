from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.repositories import get_repositories
from app.api.dependencies.use_cases import get_publish_use_case
from app.application.services.operation import OperationContext
from app.domain.entities import User
from app.domain.entities.models import AccountStatus
from app.infrastructure.security.tokens import TokenService
from app.main import create_app


@dataclass
class Users:
    user: User | None

    async def get(self, user_id: UUID) -> User | None:
        return self.user if self.user and self.user.id == user_id else None


@pytest.mark.parametrize(
    "scenario", ["valid", "missing", "invalid", "suspended", "revoked", "deleted"]
)
def test_current_profile_validates_bearer_and_account(scenario: str) -> None:
    user = User(
        username="qa-p1", full_name="QA P1", email="qa@example.test", password_hash="secret"
    )
    token = TokenService().create_access_token(user.id)
    if scenario == "suspended":
        user.account_status = AccountStatus.SUSPENDED
    if scenario == "revoked":
        user.auth_version = 1
    users = Users(None if scenario == "deleted" else user)
    application = create_app()
    application.dependency_overrides[get_repositories] = lambda: SimpleNamespace(users=users)
    client = TestClient(application)
    headers = (
        {}
        if scenario == "missing"
        else {"Authorization": f"Bearer {'bad' if scenario == 'invalid' else token}"}
    )
    response = client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == (200 if scenario == "valid" else 401)
    if scenario == "valid":
        body = response.json()
        assert body["id"] == str(user.id)
        assert body["role"] == "user"
        assert "password_hash" not in body
        assert "email" not in body


@pytest.mark.parametrize("scenario", ["valid", "missing", "other_author"])
def test_post_creation_enforces_author_on_server(scenario: str) -> None:
    from uuid import uuid4

    from app.domain.entities import Post

    user = User(username="qa-p1", full_name="QA P1", email="qa@example.test", password_hash="hash")
    operation = OperationContext("problem_01_publish_content")
    execute = AsyncMock(
        return_value=SimpleNamespace(post=Post(user_id=user.id, text="Idea"), operation=operation)
    )
    application = create_app()
    application.dependency_overrides[get_repositories] = lambda: SimpleNamespace(users=Users(user))
    application.dependency_overrides[get_publish_use_case] = lambda: SimpleNamespace(
        execute=execute
    )
    token = TokenService().create_access_token(user.id)
    response = TestClient(application).post(
        "/api/v1/posts",
        headers={} if scenario == "missing" else {"Authorization": f"Bearer {token}"},
        json={
            "user_id": str(uuid4() if scenario == "other_author" else user.id),
            "text": "Idea",
            "interests": ["datos"],
        },
    )
    assert response.status_code == {"valid": 202, "missing": 401, "other_author": 403}[scenario]
    assert execute.await_count == (1 if scenario == "valid" else 0)
