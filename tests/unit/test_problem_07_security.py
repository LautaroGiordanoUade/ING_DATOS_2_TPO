import time
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.infrastructure.security.password import PasswordHasher
from app.infrastructure.security.tokens import TokenService
from app.schemas.moderation import DecisionRequest, ReportCreate, RevertRequest


@pytest.mark.parametrize("token", ["", "not-a-token", ".", "!.no", "a.b.c", "e30=.bad"])
def test_invalid_credentials_are_rejected(token: str) -> None:
    with pytest.raises(ValueError):
        TokenService().verify_access_token(token)


def test_token_signature_expiry_and_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    actor = uuid4()
    token = TokenService().create_access_token(actor)
    assert TokenService().verify_access_token(token) == actor
    with pytest.raises(ValueError):
        TokenService().verify_access_token(token[:-1] + ("0" if token[-1] != "0" else "1"))
    future = time.time() + 4000
    monkeypatch.setattr("app.infrastructure.security.tokens.time.time", lambda: future)
    with pytest.raises(ValueError):
        TokenService().verify_access_token(token)


def test_password_hashes_use_distinct_salts_and_verify() -> None:
    hasher = PasswordHasher()
    first, second = hasher.hash("password07"), hasher.hash("password07")
    assert first != second
    assert hasher.verify("password07", first)
    assert not hasher.verify("wrong", first)
    assert not hasher.verify("password07", "malformed")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: DecisionRequest(decision="hide", reason="   "),
        lambda: RevertRequest(reason="   "),
        lambda: ReportCreate.model_validate({"post_id": str(uuid4()), "reason": "unknown"}),
    ],
)
def test_semantic_schema_validation(factory: object) -> None:
    from collections.abc import Callable
    from typing import cast

    with pytest.raises(ValidationError):
        cast(Callable[[], object], factory)()


def test_production_rejects_development_signing_key() -> None:
    with pytest.raises(ValidationError, match="AUTH_SECRET"):
        Settings(app_env="production")
