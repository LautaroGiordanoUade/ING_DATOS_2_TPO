"""Reproducciones aisladas de los cambios P5 recibidos desde main; no modifica datos reales."""

import asyncio
import os
from typing import Any

import pytest

from app.core.exceptions import ConflictError
from app.domain.entities import Comment, Reaction
from app.infrastructure.persistence.mongodb.repositories.content_repositories import (
    MongoReactionRepository,
)
from app.infrastructure.persistence.redis.accounts import RedisAccountViews
from app.infrastructure.persistence.redis.reaction_lock import RedisReactionLock
from app.infrastructure.persistence.redis.repositories.operational_repositories import (
    RedisCounterRepository,
)
from tests.integration.support import Harness
from tests.integration.support import harness as harness

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires all three real engines"
)


@pytest.mark.parametrize(
    "action,collection,namespace",
    [
        ("reaction", "reactions", "post_reactions"),
        ("comment", "comments", "post_comments"),
    ],
)
async def test_compensation_restores_real_mongo_and_redis(
    harness: Harness,
    action: str,
    collection: str,
    namespace: str,
) -> None:
    h = harness
    await h.resources.redis.set(f"{namespace}:{h.post.id}:count", 0)
    payload = {"post_id": str(h.post.id), "user_id": str(h.user.id)}
    payload["kind" if action == "reaction" else "text"] = "like" if action == "reaction" else "QA"
    response = await h.client.post(
        f"/api/v1/problems/5/{action}",
        json=payload,
        headers={"X-Fail-At-Step": "redis_publish_notification"},
    )
    assert response.status_code == 500, response.text
    actual_mongo = await h.posts._database[collection].count_documents({"post_id": str(h.post.id)})
    actual_redis = int(await h.resources.redis.get(f"{namespace}:{h.post.id}:count") or 0)
    assert (actual_mongo, actual_redis) == (0, 0)


async def test_remove_uncertain_counter_ack_compensates_exactly(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = harness
    await h.resources.redis.set(f"post_reactions:{h.post.id}:count", 0)
    payload = {"post_id": str(h.post.id), "user_id": str(h.user.id), "kind": "like"}
    assert (await h.client.post("/api/v1/problems/5/reaction", json=payload)).status_code == 202
    original = RedisCounterRepository.increment

    async def uncertain(
        self: RedisCounterRepository, namespace: str, identifier: Any, amount: int = 1
    ) -> int:
        result = await original(self, namespace, identifier, amount)
        if amount == -1:
            raise ConnectionError("Redis aplico el decremento pero se perdio la respuesta")
        return result

    monkeypatch.setattr(RedisCounterRepository, "increment", uncertain)
    response = await h.client.request(
        "DELETE",
        "/api/v1/problems/5/reaction",
        json={"post_id": str(h.post.id), "user_id": str(h.user.id)},
    )
    assert response.status_code == 503, response.text
    total = await h.posts._database["reactions"].count_documents({"post_id": str(h.post.id)})
    counter = int(await h.resources.redis.get(f"post_reactions:{h.post.id}:count") or 0)
    assert (total, counter) == (1, 1)


@pytest.mark.parametrize("gate", ["moderation", "suspension"])
async def test_reconciliation_respects_p7_p8_gates(harness: Harness, gate: str) -> None:
    h = harness
    if gate == "moderation":
        snapshot = await h.views.snapshot(h.post.id)
        await h.views.hide(h.post.id)
    else:
        views = RedisAccountViews(h.resources.redis)
        snapshot = await views.snapshot(h.post.id)
        await views.hide_post(h.post.id, snapshot)
    counters = RedisCounterRepository(h.resources.redis)
    assert (await counters.get_many("post_reactions", (h.post.id,)))[h.post.id] == 0
    await counters.set_value("post_reactions", h.post.id, 3)
    assert (await counters.get_many("post_reactions", (h.post.id,)))[h.post.id] == 0
    if gate == "moderation":
        await h.views.restore(h.post.id, snapshot)
    else:
        await views.restore_post(h.post.id, snapshot)
    assert (await counters.get_many("post_reactions", (h.post.id,)))[h.post.id] == 3


async def test_expired_orphan_lock_reconciles_before_next_writer(harness: Harness) -> None:
    h = harness
    repository = MongoReactionRepository(h.posts._database)
    await repository.upsert(Reaction(post_id=h.post.id, user_id=h.user.id, kind="like"))
    await h.resources.redis.set(f"post_reactions:{h.post.id}:count", 0)
    await h.resources.redis.set(f"lock:post_reactions:{h.post.id}", "crashed-writer", px=10)
    await h.resources.redis.set(f"lock_active:post_reactions:{h.post.id}", "1", ex=60)
    await asyncio.sleep(0.03)
    response = await h.client.post(
        "/api/v1/problems/5/reaction",
        json={
            "post_id": str(h.post.id),
            "user_id": str(h.user.id),
            "kind": "love",
        },
    )
    assert response.status_code == 202, response.text
    total = await repository.count_for_post(h.post.id)
    counter = int(await h.resources.redis.get(f"post_reactions:{h.post.id}:count") or 0)
    assert (total, counter) == (1, 1)


@pytest.mark.parametrize("action", ["change", "delete"])
async def test_uncertain_mongo_write_restores_previous_reaction(
    harness: Harness,
    action: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = harness
    repository = MongoReactionRepository(h.posts._database)
    old = Reaction(post_id=h.post.id, user_id=h.user.id, kind="like")
    await repository.upsert(old)
    await h.resources.redis.set(f"post_reactions:{h.post.id}:count", 1)
    method = "upsert" if action == "change" else "delete_for_user"
    original = getattr(MongoReactionRepository, method)
    attempted = False

    async def uncertain(self: MongoReactionRepository, *args: Any) -> Any:
        nonlocal attempted
        result = await original(self, *args)
        if not attempted:
            attempted = True
            raise ConnectionError("Mongo aplico la escritura; respuesta perdida")
        return result

    monkeypatch.setattr(MongoReactionRepository, method, uncertain)
    payload = {"post_id": str(h.post.id), "user_id": str(h.user.id)}
    if action == "change":
        payload["kind"] = "love"
    response = await h.client.request(
        "POST" if action == "change" else "DELETE", "/api/v1/problems/5/reaction", json=payload
    )
    assert response.status_code == 503
    restored = await repository.get_for_user(h.post.id, h.user.id)
    assert restored is not None and restored.id == old.id and restored.kind == "like"
    assert int(await h.resources.redis.get(f"post_reactions:{h.post.id}:count") or 0) == 1


async def test_failed_comment_and_concurrent_success_do_not_overwrite_each_other(
    harness: Harness,
) -> None:
    h = harness
    await h.resources.redis.set(f"post_comments:{h.post.id}:count", 0)
    payload = {"post_id": str(h.post.id), "user_id": str(h.user.id), "text": "QA"}
    failed, succeeded = await asyncio.gather(
        h.client.post(
            "/api/v1/problems/5/comment",
            json=payload,
            headers={"X-Fail-At-Step": "redis_publish_notification"},
        ),
        h.client.post("/api/v1/problems/5/comment", json={**payload, "text": "keep"}),
    )
    assert failed.status_code == 500 and succeeded.status_code == 202
    count = await h.posts._database["comments"].count_documents({"post_id": str(h.post.id)})
    assert count == 1
    assert int(await h.resources.redis.get(f"post_comments:{h.post.id}:count") or 0) == count


async def test_orphaned_comment_counter_is_repaired_before_next_write(harness: Harness) -> None:
    from app.infrastructure.persistence.mongodb.repositories.content_repositories import (
        MongoCommentRepository,
    )

    h = harness
    await MongoCommentRepository(h.posts._database).create(
        Comment(post_id=h.post.id, user_id=h.user.id, text="persisted before crash")
    )
    await h.resources.redis.set(f"post_comments:{h.post.id}:count", 0)
    response = await h.client.post(
        "/api/v1/problems/5/comment",
        json={
            "post_id": str(h.post.id),
            "user_id": str(h.user.id),
            "text": "after crash",
        },
    )
    assert response.status_code == 202
    assert int(await h.resources.redis.get(f"post_comments:{h.post.id}:count") or 0) == 2


async def test_expired_redis_lease_does_not_admit_a_second_writer(harness: Harness) -> None:
    h = harness
    first = RedisReactionLock(h.resources.redis, lease_seconds=0.08, blocking_timeout=0.05)
    second = RedisReactionLock(h.resources.redis, lease_seconds=0.08, blocking_timeout=0.05)
    async with first.hold(h.post.id):
        await asyncio.sleep(0.12)  # Expired lease, but the original writer is still alive.
        assert not await h.resources.redis.exists(f"lock:post_reactions:{h.post.id}")
        with pytest.raises(ConflictError):
            async with second.hold(h.post.id):
                pytest.fail("A second writer overlapped the paused owner")
    async with second.hold(h.post.id):
        assert await h.resources.redis.exists(f"lock:post_reactions:{h.post.id}")


async def test_process_crash_releases_host_lock_and_next_writer_repairs_counters(
    harness: Harness,
) -> None:
    import sys

    h = harness
    await MongoReactionRepository(h.posts._database).upsert(
        Reaction(post_id=h.post.id, user_id=h.user.id, kind="like")
    )
    await h.resources.redis.set(f"post_reactions:{h.post.id}:count", 0)
    source = """import asyncio, sys
from uuid import UUID
from app.core.config import get_settings
from app.infrastructure.persistence.redis.client import create_redis_client
from app.infrastructure.persistence.redis.reaction_lock import RedisReactionLock
async def main():
    redis = create_redis_client(get_settings().redis_url)
    async with RedisReactionLock(redis, lease_seconds=0.15).hold(UUID(sys.argv[1])):
        print('LOCKED', flush=True)
        await asyncio.Event().wait()
asyncio.run(main())
"""
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        source,
        str(h.post.id),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert child.stdout is not None
        assert await asyncio.wait_for(child.stdout.readline(), 5) == b"LOCKED\n"
    finally:
        if child.returncode is None:
            child.kill()
        await child.wait()
    await asyncio.sleep(0.2)
    response = await h.client.post(
        "/api/v1/problems/5/reaction",
        json={
            "post_id": str(h.post.id),
            "user_id": str(h.user.id),
            "kind": "love",
        },
    )
    assert response.status_code == 202, response.text
    assert int(await h.resources.redis.get(f"post_reactions:{h.post.id}:count") or 0) == 1


async def test_crashed_operation_is_durably_recovered(harness: Harness) -> None:
    from app.application.services.operation import OperationContext, OperationStatus

    h = harness
    post = h.post
    actor = h.user
    reaction = Reaction(post_id=post.id, user_id=actor.id, kind="like")
    await MongoReactionRepository(h.posts._database).upsert(reaction)
    await h.resources.redis.set(f"post_reactions:{post.id}:count", 0)

    # Simulate an operation left in RUNNING status after a crash
    operation = OperationContext(
        operation_type="problem_05_react",
        status=OperationStatus.RUNNING,
        current_step="redis_publish_notification",
        completed_steps=["mongo_upsert_reaction"],
        metadata={
            "post_id": str(post.id),
            "user_id": str(actor.id),
            "author_id": str(post.user_id),
            "event_id": str(reaction.id),
            "kind": "like",
        },
    )
    await h.resources.operation_log.save(operation)

    # Next writer interacts with the post
    response = await h.client.post(
        "/api/v1/problems/5/reaction",
        json={
            "post_id": str(post.id),
            "user_id": str(actor.id),
            "kind": "love",
        },
    )
    assert response.status_code == 202

    # Verify the crashed operation was recovered and marked COMPLETED
    recovered_op = await h.resources.operation_log.get(operation.operation_id)
    assert recovered_op is not None
    assert recovered_op.status == OperationStatus.COMPLETED
