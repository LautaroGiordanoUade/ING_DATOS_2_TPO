from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.application.services.account_job import AccountJob
from app.infrastructure.security.tokens import TokenService
from app.schemas.accounts import AccountDecision


@pytest.mark.parametrize(
    "payload",
    [
        {"reason": ""},
        {"reason": "   "},
        {"reason": "x" * 1001},
        {"reason": "test", "role": "admin"},
        {},
    ],
)
def test_account_decision_validation(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        AccountDecision.model_validate(payload)


@pytest.mark.parametrize("version", [0, 1, 5])
def test_signed_tokens_preserve_account_version(version: int) -> None:
    service = TokenService()
    user_id = uuid4()
    token = service.create_access_token(user_id, version)
    assert service.verify_access_token(token) == user_id
    assert service.token_version(token) == version


def test_durable_account_job_json_round_trip() -> None:
    job = AccountJob(
        operation_id=uuid4(),
        user_id=uuid4(),
        actor_id=uuid4(),
        action="suspend",
        reason="test",
        post_ids=[uuid4()],
        previous_status="active",
        graph_snapshot={"exists": False, "account_status": None},
    )
    recovered = AccountJob.model_validate_json(job.model_dump_json())
    assert recovered == job
    assert recovered.created_at.tzinfo is not None


def test_invalid_account_action_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AccountJob.model_validate(
            {
                "operation_id": str(uuid4()),
                "user_id": str(uuid4()),
                "actor_id": str(uuid4()),
                "action": "delete",
                "reason": "test",
            }
        )
