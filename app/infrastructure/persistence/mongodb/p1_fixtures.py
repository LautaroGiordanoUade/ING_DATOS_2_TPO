"""Development fixtures and additive migration for the original P1 seed."""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pymongo.asynchronous.database import AsyncDatabase

from app.domain.entities import User
from app.domain.entities.models import AccountStatus

DISABLED_PASSWORD = "!qa-p1-fixture-login-disabled"


def fixture_user_document(identifier: str, *, suspended: bool = False) -> dict[str, Any]:
    user = User(
        id=UUID(identifier),
        username=f"qa-p1-{identifier}",
        full_name=f"P1 fixture {identifier}",
        email=f"qa-p1-{identifier}@example.test",
        password_hash=DISABLED_PASSWORD,
        account_status=AccountStatus.SUSPENDED if suspended else AccountStatus.ACTIVE,
    )
    document = asdict(user)
    document["_id"] = str(document.pop("id"))
    return document


def missing_fixture_fields(document: dict[str, Any]) -> dict[str, Any]:
    """Only exact qa-p1-UUID fixtures; never replace existing non-null values."""
    identifier = document.get("_id")
    if not isinstance(identifier, str) or document.get("username") != f"qa-p1-{identifier}":
        return {}
    try:
        defaults = fixture_user_document(identifier)
    except ValueError:
        return {}
    return {
        field: value
        for field, value in defaults.items()
        if field not in ("_id", "username")
        and (field not in document or (document[field] is None and value is not None))
    }


async def migrate_p1_fixtures(
    database: AsyncDatabase[dict[str, Any]], *, apply: bool = False
) -> dict[str, int | bool]:
    candidates = needs_update = modified = 0
    async for document in database["users"].find({"username": {"$regex": "^qa-p1-"}}):
        candidates += 1
        patch = missing_fixture_fields(document)
        if not patch:
            continue
        needs_update += 1
        if not apply:
            continue
        # One original snapshot per fixture. A rerun never overwrites the backup.
        await database["qa_p1_user_backups"].update_one(
            {"_id": document["_id"]},
            {
                "$setOnInsert": {
                    "document": document,
                    "backed_up_at": datetime.now(UTC),
                    "migration": "complete-p1-fixture-users-v1",
                }
            },
            upsert=True,
        )
        expected = {field: document.get(field) for field in patch}
        result = await database["users"].update_one(
            {"_id": document["_id"], "username": document["username"], **expected},
            {"$set": patch},
        )
        if result.matched_count != 1:
            raise RuntimeError("Fixture changed concurrently; rerun migration after reviewing it")
        modified += result.modified_count
    return {
        "apply": apply,
        "candidates": candidates,
        "needs_update": needs_update,
        "modified": modified,
    }
