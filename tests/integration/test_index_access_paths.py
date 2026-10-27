"""Real optimizer plans and uniqueness, including legacy documents outside partial indexes."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pymongo.errors import DuplicateKeyError

from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.mongodb.indexes import ensure_mongo_indexes
from app.tools.audit_indexes import summarize_plan

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires real MongoDB"
)


async def test_history_index_covers_first_page_cursor_and_legacy_without_losing_uniqueness():
    client = create_mongo_client(get_settings().mongodb_url)
    name = "test_index_history_" + uuid4().hex
    db = client[name]
    try:
        await ensure_mongo_indexes(db)
        await ensure_mongo_indexes(db)
        await db.messages.insert_many(
            [
                {"_id": f"{group}:{sequence}", "conversation_id": group, "sequence": sequence}
                for group in range(40)
                for sequence in range(1, 81)
            ]
        )
        # Neither absence nor null participates in the numeric unique constraint.
        await db.messages.insert_many(
            [
                {"_id": "old-1", "conversation_id": 0},
                {"_id": "old-2", "conversation_id": 0},
                {"_id": "null-1", "conversation_id": 0, "sequence": None},
                {"_id": "null-2", "conversation_id": 0, "sequence": None},
            ]
        )
        for boundary in ({"$exists": True}, {"$lt": 50}):
            command = {
                "find": "messages",
                "filter": {"conversation_id": 0, "sequence": boundary},
                "sort": {"sequence": -1},
                "limit": 21,
            }
            explained = await db.command("explain", command, verbosity="executionStats")
            plan = summarize_plan(explained)
            assert plan["indexes"] == ["ix_message_history"]
            assert "SORT" not in plan["stages"] and "COLLSCAN" not in plan["stages"]
            assert plan["documents_examined"] <= 22
            natural = (
                await db.messages.find(command["filter"])
                .sort("sequence", -1)
                .limit(21)
                .hint([("$natural", 1)])
                .to_list()
            )
            indexed = await (
                db.messages.find(command["filter"]).sort("sequence", -1).limit(21).to_list()
            )
            assert indexed == natural
        with pytest.raises(DuplicateKeyError):
            await db.messages.insert_one({"_id": "duplicate", "conversation_id": 0, "sequence": 1})
    finally:
        await client.drop_database(name)
        await client.close()


async def test_author_order_and_publication_lookup_use_indexes_without_hints():
    client = create_mongo_client(get_settings().mongodb_url)
    name = "test_index_publications_" + uuid4().hex
    db = client[name]
    try:
        await ensure_mongo_indexes(db)
        timestamp = datetime.now(UTC)
        await db.posts.insert_many(
            [
                {
                    "_id": f"{i:05}",
                    "user_id": str(i % 40),
                    "published_at": timestamp,
                    "visibility": "public",
                    "publication_state": "published",
                    "moderation_status": "visible",
                }
                for i in range(3200)
            ]
        )
        await db.publication_jobs.insert_many(
            [
                {
                    "_id": str(i),
                    "post": {"id": str(i), "user_id": str(i % 40)},
                    "operation": {"status": "completed"},
                }
                for i in range(3200)
            ]
        )
        command = {
            "find": "posts",
            "filter": {
                "user_id": "0",
                "visibility": "public",
                "publication_state": {"$ne": "pending"},
                "moderation_status": {"$ne": "hidden"},
            },
            "sort": {"published_at": -1, "_id": -1},
            "limit": 20,
        }
        plan = summarize_plan(await db.command("explain", command, verbosity="executionStats"))
        assert plan["indexes"] == ["ix_post_author_published_id"]
        assert "SORT" not in plan["stages"]
        assert plan["documents_examined"] == 20
        for query, index in (
            ({"post.id": "100"}, "ix_publication_post"),
            (
                {"post.user_id": "0", "operation.status": {"$in": ["pending", "running"]}},
                "ix_publication_author_status",
            ),
        ):
            plan = summarize_plan(
                await db.command(
                    "explain",
                    {
                        "find": "publication_jobs",
                        "filter": query,
                        "limit": 100,
                    },
                    verbosity="executionStats",
                )
            )
            assert plan["indexes"] == [index]
            assert plan["documents_examined"] <= 1
    finally:
        await client.drop_database(name)
        await client.close()
