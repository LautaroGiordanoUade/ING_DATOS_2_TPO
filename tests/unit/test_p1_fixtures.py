from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities.models import AccountStatus
from app.infrastructure.persistence.mongodb.p1_fixtures import (
    fixture_user_document,
    missing_fixture_fields,
)
from app.infrastructure.persistence.mongodb.repositories.identity import MongoUserRepository
from app.infrastructure.security.password import PasswordHasher


def test_fixture_is_a_complete_user_with_unique_email_and_disabled_login() -> None:
    identifier = str(uuid4())
    document = fixture_user_document(identifier)
    user = MongoUserRepository._user(document)
    assert str(user.id) == identifier
    assert user.email != fixture_user_document(str(uuid4()))["email"]
    assert user.role == "user"
    assert not PasswordHasher().verify("anything", user.password_hash)


def test_migration_fills_only_missing_fields_and_is_idempotent() -> None:
    identifier = str(uuid4())
    created = datetime(2026, 1, 1, tzinfo=UTC)
    original = {
        "_id": identifier,
        "username": f"qa-p1-{identifier}",
        "account_status": "suspended",
        "registered_at": created,
        "password_hash": "existing",
        "role": "moderator",
        "auth_version": 9,
    }
    patch = missing_fixture_fields(original)
    assert "_id" not in patch and "username" not in patch
    assert "password_hash" not in patch and "account_status" not in patch
    assert "registered_at" not in patch and "role" not in patch and "auth_version" not in patch
    completed = {**original, **patch}
    assert missing_fixture_fields(completed) == {}
    assert MongoUserRepository._user(completed).account_status == AccountStatus.SUSPENDED


def test_migration_ignores_real_users_and_malformed_fixture_identifiers() -> None:
    assert missing_fixture_fields({"_id": str(uuid4()), "username": "real-user"}) == {}
    assert missing_fixture_fields({"_id": "bad", "username": "qa-p1-bad"}) == {}
    assert missing_fixture_fields({"_id": str(uuid4()), "username": "qa-p1-other"}) == {}


def test_null_email_is_replaced_but_existing_email_is_preserved() -> None:
    identifier = str(uuid4())
    original = {"_id": identifier, "username": f"qa-p1-{identifier}", "email": None}
    assert missing_fixture_fields(original)["email"].endswith("@example.test")
    original["email"] = "existing@example.test"
    assert "email" not in missing_fixture_fields(original)
