"""Offline recovery on real engines; source DB is isolated and targets must start empty."""

import json
import os
import secrets
from collections.abc import AsyncIterator
from uuid import UUID, uuid4, uuid5

import pytest

from app.application.services.account_job import AccountJob
from app.application.services.account_processor import AccountProcessor
from app.application.services.moderation_job import ModerationJob
from app.application.services.moderation_processor import ModerationProcessor
from app.core.config import get_settings
from app.domain.entities import ModerationReport
from app.infrastructure.persistence.mongodb.repositories.accounts import MongoAccountStore
from app.infrastructure.persistence.mongodb.repositories.moderation import MongoModerationRepository
from app.infrastructure.persistence.neo4j.repositories import Neo4jSocialGraphRepository
from app.infrastructure.persistence.redis.accounts import RedisAccountViews
from app.infrastructure.persistence.redis.moderation import RedisModerationViews
from app.infrastructure.persistence.redis.publication_feeds import RedisPublicationFeeds
from app.tools.dataset import Dataset, SeedOptions
from app.tools.rebuild_redis import MARKER, RecoverySources, rebuild_lock, recover
from app.tools.seed_data import DatasetStore

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires isolated real MongoDB/Neo4j/Redis"
)


@pytest.fixture
async def recovery() -> AsyncIterator[tuple[DatasetStore, DatasetStore, Dataset]]:
    options = SeedOptions(
        users=12,
        posts=40,
        comments=10,
        reactions=20,
        conversations=2,
        messages=20,
        reports=0,
        seed=10000 + secrets.randbelow(900000),
    )
    data = Dataset(options)
    name = "test_redis_rebuild_" + uuid4().hex
    settings = get_settings().model_copy(update={"mongodb_database": name})
    base = settings.redis_url.rsplit("/", 1)[0]
    source = DatasetStore(settings.model_copy(update={"redis_url": base + "/14"}), data)
    target = DatasetStore(settings.model_copy(update={"redis_url": base + "/15"}), data)
    owned = False
    try:
        assert await source.redis.dbsize() == 0 and await target.redis.dbsize() == 0, (
            "Reserved test DB14/DB15 must be empty; no existing data is removed"
        )
        owned = True
        await source.load(secrets.token_urlsafe(20))
        yield source, target, data
    finally:
        if owned:
            for store in (source, target):
                keys = [key async for key in store.redis.scan_iter()]
                if keys:
                    await store.redis.delete(*keys)
            async with source.graph.session() as session:
                await (
                    await session.run(
                        "MATCH (u:User) WHERE u.id IN $ids DETACH DELETE u",
                        ids=data.users,
                    )
                ).consume()
            await source.mongo.drop_database(name)
        await source.close()
        await target.close()


async def test_rebuild_feeds_counters_unread_and_preserve_sources(recovery):
    source, target, data = recovery
    original = {
        name: await source.db[name].find().sort("_id", 1).to_list()
        for name in await source.db.list_collection_names()
    }
    plan = await recover(target)
    assert plan["status"] == "plan" and await target.redis.dbsize() == 0
    result = await recover(target, apply=True, offline=True)
    assert result["status"] == "completed" and result["fingerprint"] == plan["fingerprint"]
    for actor in data.users:
        assert await target.redis.zrange(f"feed:{actor}", 0, -1, withscores=True) == (
            await source.redis.zrange(f"feed:{actor}", 0, -1, withscores=True)
        )
    for pattern in (
        "post_*:count",
        "followers:*:count",
        "following:*:count",
        "conversation:*:unread:*",
    ):
        async for key in source.redis.scan_iter(match=pattern):
            assert await target.redis.get(key) == await source.redis.get(key)
    assert not [key async for key in target.redis.scan_iter(match="user:*:notifications")]
    assert not [key async for key in target.redis.scan_iter(match="presence:*")]
    checked = await recover(target, verify=True, offline=True)
    assert checked["verified_commands"] == plan["commands"]
    await target.redis.set(f"post_comments:{data.posts[0]}:count", 999)
    with pytest.raises(ValueError, match="diferente"):
        await recover(target, verify=True, offline=True)
    for name, documents in original.items():
        assert await source.db[name].find().sort("_id", 1).to_list() == documents


@pytest.mark.parametrize(
    "collection,document",
    [
        ("publication_jobs", {"operation": {"status": "running"}}),
        ("follow_jobs", {"status": "failed"}),
        ("moderation_jobs", {"status": "compensating"}),
        ("account_jobs", {"status": "pending"}),
        ("operations", {"status": "running"}),
        ("messages", {"delivery_status": "pending"}),
        ("conversations", {"redis_pending": True}),
        ("seed_datasets", {"status": "loading"}),
    ],
)
async def test_nonterminal_sources_refused_without_target_writes(recovery, collection, document):
    _, target, _ = recovery
    await target.db[collection].insert_one({"_id": str(uuid4()), **document})
    with pytest.raises(ValueError):
        await recover(target, apply=True, offline=True)
    assert await target.redis.dbsize() == 0


async def test_offline_empty_target_and_resume_guards(recovery):
    _, target, _ = recovery
    with pytest.raises(ValueError, match="offline"):
        await recover(target, apply=True)
    await target.redis.set("unrelated", "preserve")
    with pytest.raises(ValueError, match="vacío"):
        await recover(target, apply=True, offline=True)
    assert await target.redis.get("unrelated") == b"preserve"
    assert await target.redis.dbsize() == 1
    await target.redis.delete("unrelated")  # This test owns the initially empty target.
    sources = await RecoverySources.load(target)
    plan = sources.plan()
    # Simulate loss of the tool between two acknowledged batches.
    await target.redis.set(
        MARKER, json.dumps({"status": "running", "fingerprint": plan["fingerprint"]})
    )
    pipe = target.redis.pipeline(transaction=False)
    for command in list(sources.commands())[:17]:
        pipe.execute_command(*command)
    await pipe.execute()
    with rebuild_lock(), pytest.raises(ValueError, match="Otra reconstrucción"):
        await recover(target, apply=True, offline=True, resume=True)
    marker = json.loads(await target.redis.get(MARKER))
    await target.redis.set(MARKER, json.dumps({**marker, "fingerprint": "different"}))
    with pytest.raises(ValueError, match="mismas fuentes"):
        await recover(target, apply=True, offline=True, resume=True)
    await target.redis.set(MARKER, json.dumps(marker))
    result = await recover(target, apply=True, offline=True, resume=True)
    assert result["status"] == "completed"
    with pytest.raises(ValueError, match="interrumpida"):
        await recover(target, apply=True, offline=True, resume=True)


async def test_hidden_suspended_and_unfollowed_snapshots_remain_safe_after_rebuild(recovery):
    source, target, data = recovery
    author, reader, former, suspended = map(
        UUID, (data.users[0], data.users[1], data.users[6], data.users[5])
    )
    post = UUID(data.posts[0])
    moderator = UUID(data.users[3])
    moderation = MongoModerationRepository(source.db)
    report = ModerationReport(post_id=post, reporter_id=reader, reason="spam")
    await moderation.create_report(report)
    hide = await moderation.enqueue(
        ModerationJob(
            operation_id=uuid5(report.id, "decision"),
            report_id=report.id,
            post_id=post,
            moderator_id=moderator,
            action="hide",
            reason="Recovery test",
        )
    )
    await ModerationProcessor(moderation, RedisModerationViews(source.redis)).process(hide)
    assert hide.status == "completed"
    # A later unfollow is absent from the graph, but still present in the old hide snapshot.
    async with source.graph.session() as session:
        await (
            await session.run(
                "MATCH (:User {id:$f})-[r:FOLLOWS]->(:User {id:$a}) DELETE r",
                f=str(former),
                a=str(author),
            )
        ).consume()
    accounts = MongoAccountStore(source.db)
    graph = Neo4jSocialGraphRepository(source.graph)
    suspend = await accounts.enqueue(
        AccountJob(
            operation_id=uuid4(),
            user_id=suspended,
            actor_id=moderator,
            action="suspend",
            reason="Recovery test",
        ),
        keyed=True,
    )
    await AccountProcessor(accounts, graph, RedisAccountViews(source.redis)).process(suspend)
    assert suspend.status == "completed"
    await recover(target, apply=True, offline=True)
    assert await target.redis.get(f"moderation:{post}:hidden") == b"hidden"
    assert await target.redis.get(f"post_reactions:{post}:count") == b"0"
    assert await target.redis.get(f"post_reactions:{post}:count:moderation_saved") == b"1"
    assert await target.redis.get(f"account:{suspended}:suspended") == b"suspended"
    assert await target.redis.zcard(f"feed:{suspended}") == 0
    assert await target.redis.get(f"follow:{former}:{author}:state") == b"none"
    # Run the actual P7 revert and P8 reactivation against the rebuilt Redis.
    revert = await moderation.enqueue(
        ModerationJob(
            operation_id=uuid4(),
            report_id=report.id,
            post_id=post,
            moderator_id=moderator,
            action="revert",
            reason="Recovery test",
            restore=hide.snapshot,
        )
    )
    await ModerationProcessor(moderation, RedisModerationViews(target.redis)).process(revert)
    assert revert.status == "completed"
    assert await target.redis.zscore(f"feed:{reader}", str(post)) is not None
    assert await target.redis.zscore(f"feed:{former}", str(post)) is None
    assert await target.redis.get(f"post_reactions:{post}:count") == b"1"
    reactivate = await accounts.enqueue(
        AccountJob(
            operation_id=uuid4(),
            user_id=suspended,
            actor_id=moderator,
            action="reactivate",
            reason="Recovery test",
        ),
        keyed=True,
    )
    await AccountProcessor(accounts, graph, RedisAccountViews(target.redis)).process(reactivate)
    assert reactivate.status == "completed"
    assert await target.redis.get(f"account:{suspended}:suspended") is None
    assert await target.redis.zcard(f"feed:{suspended}") > 0
    assert not await RedisAccountViews(target.redis).presence(suspended)
    assert await RedisPublicationFeeds(target.redis).visible_ids(reader)
