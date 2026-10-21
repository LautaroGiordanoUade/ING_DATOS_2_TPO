import os
from copy import deepcopy
from typing import Any
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.mongodb.p1_fixtures import migrate_p1_fixtures
from app.infrastructure.persistence.mongodb.repositories.identity import MongoUserRepository
from app.workers.initialize_data import initialize_database

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires real MongoDB"
)


async def test_additive_migration_backup_dry_run_and_replay_on_real_mongo() -> None:
    client = create_mongo_client(get_settings().mongodb_url)
    name = "test_p1_migration_" + uuid4().hex
    db = client[name]
    identifier = str(uuid4())
    original = {
        "_id": identifier,
        "username": f"qa-p1-{identifier}",
        "account_status": "suspended",
        "role": "user",
        "auth_version": 5,
    }
    unrelated: dict[str, Any] = {
        "_id": str(uuid4()),
        "username": "unrelated-user",
        "email": "other@test.example",
    }
    try:
        await db["users"].insert_many([deepcopy(original), deepcopy(unrelated)])
        await db["posts"].insert_one({"_id": "existing-post", "user_id": identifier})
        preview = await migrate_p1_fixtures(db)
        assert preview["needs_update"] == 1 and preview["modified"] == 0
        assert await db["qa_p1_user_backups"].count_documents({}) == 0
        assert await db["users"].find_one({"_id": identifier}) == original
        result = await migrate_p1_fixtures(db, apply=True)
        assert result["modified"] == 1
        migrated = await db["users"].find_one({"_id": identifier})
        assert migrated is not None
        assert str(MongoUserRepository._user(migrated).id) == identifier
        assert migrated["account_status"] == "suspended" and migrated["auth_version"] == 5
        assert await db["users"].find_one({"_id": unrelated["_id"]}) == unrelated
        assert await db["posts"].count_documents({"user_id": identifier}) == 1
        backup = await db["qa_p1_user_backups"].find_one({"_id": identifier})
        assert backup is not None and backup["document"] == original
        replay = await migrate_p1_fixtures(db, apply=True)
        assert replay["modified"] == replay["needs_update"] == 0
        assert await db["qa_p1_user_backups"].count_documents({}) == 1
        assert await db["users"].find_one({"_id": identifier}) == migrated
        await MongoUserRepository(db).ensure_indexes()
    finally:
        assert name.startswith("test_p1_migration_")
        await client.drop_database(name)
        await client.close()


@pytest.mark.parametrize("mode", ["empty", "legacy", "production", "duplicate"])
async def test_compose_initializer_on_real_mongo(mode: str) -> None:
    from pymongo.errors import DuplicateKeyError

    client = create_mongo_client(get_settings().mongodb_url)
    name = "test_p1_init_" + uuid4().hex
    db = client[name]
    identifier = str(uuid4())
    legacy: dict[str, Any] = {"_id": identifier, "username": f"qa-p1-{identifier}"}
    try:
        if mode in ("legacy", "production"):
            await db["users"].insert_one(dict(legacy))
        if mode == "duplicate":
            await db["users"].insert_many(
                [
                    {
                        "_id": str(uuid4()),
                        "username": f"real-user-{i}",
                        "email": "same@example.test",
                    }
                    for i in range(2)
                ]
            )
            with pytest.raises(DuplicateKeyError):
                await initialize_database(db, development=True)
            return
        result = await initialize_database(db, development=mode != "production")
        assert result["indexes_verified"] is True
        indexes = await db["users"].index_information()
        assert indexes["email_1"]["unique"] and indexes["username_1"]["unique"]
        if mode == "empty":
            assert await db["users"].count_documents({}) == 0
        elif mode == "production":
            assert result["fixture_migration"] is None
            assert await db["users"].find_one({"_id": identifier}) == legacy
            assert await db["qa_p1_user_backups"].count_documents({}) == 0
        else:
            assert result["fixture_migration"]["modified"] == 1
            second = await initialize_database(db, development=True)
            assert second["fixture_migration"]["modified"] == 0
            assert await db["qa_p1_user_backups"].count_documents({}) == 1
    finally:
        assert name.startswith("test_p1_init_")
        await client.drop_database(name)
        await client.close()
