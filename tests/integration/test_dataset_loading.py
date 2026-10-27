import os
import secrets
from dataclasses import replace
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.tools.dataset import Dataset, SeedOptions
from app.tools.seed_data import DatasetStore, dataset_lock

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires real MongoDB/Neo4j/Redis"
)


async def test_resume_verify_and_replay_preserve_existing_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = Dataset(
        SeedOptions(
            users=12,
            posts=40,
            comments=20,
            reactions=80,
            messages=30,
            conversations=4,
            reports=3,
            seed=secrets.randbelow(900_000) + 1000,
        )
    )
    store = DatasetStore(get_settings(), data)
    password = secrets.token_urlsafe(20)
    original_graph = store.load_graph
    try:
        with dataset_lock(data), pytest.raises(RuntimeError, match="Otra carga"):
            await store.load(password)
        outsider = {
            **next(data.user_documents()),
            "_id": str(uuid4()),
            "username": f"outsider_{uuid4().hex}",
            "email": f"{uuid4().hex}@example.test",
            "seed_dataset": "unrelated",
            "password_hash": "do-not-change",
        }
        await store.db.users.insert_one(outsider)
        saved_outsider = await store.db.users.find_one({"_id": outsider["_id"]})

        async def interrupt() -> None:
            raise RuntimeError("Injected interruption after MongoDB")

        monkeypatch.setattr(store, "load_graph", interrupt)
        with pytest.raises(RuntimeError, match="Injected"):
            await store.load(password)
        assert (await store.db.seed_datasets.find_one({"_id": data.name}))["status"] == "loading"
        monkeypatch.setattr(store, "load_graph", original_graph)
        with pytest.raises(ValueError, match="misma SEED_PASSWORD"):
            await store.load("a-different-password")
        result = await store.load(password)
        assert result["status"] == "completed"
        assert result["verification"]["counts"]["posts"] == 40
        assert result["verification"]["message_sequences_and_unread"]
        assert not result["verification"]["meets_requirement"]
        assert (await store.db.users.find_one({"_id": outsider["_id"]})) == saved_outsider

        await store.redis.set(f"post_comments:{data.posts[0]}:count", 999)
        with pytest.raises(RuntimeError, match="Contadores"):
            await store.verify()
        await store.load_redis()
        await store.verify()
        group = next(data.group_documents())
        await store.redis.set(
            f"conversation:{group['_id']}:unread:{group['participant_ids'][0]}", 999
        )
        with pytest.raises(RuntimeError, match="unread"):
            await store.verify()
        await store.load_redis()

        await store.db.posts.update_one(
            {"_id": data.posts[0]}, {"$set": {"text": "Edited after demo"}}
        )
        replay = await store.load("not-used-after-completion")
        assert replay["status"] == "already_loaded"
        assert (await store.db.posts.find_one({"_id": data.posts[0]}))[
            "text"
        ] == "Edited after demo"
        assert await store.db.posts.count_documents({"seed_dataset": data.name}) == 40
        mismatch = DatasetStore(get_settings(), Dataset(replace(data.options, comments=21)))
        try:
            with pytest.raises(RuntimeError, match="otra configuración"):
                await mismatch.load(password)
        finally:
            await mismatch.close()
    finally:
        await store.close()
