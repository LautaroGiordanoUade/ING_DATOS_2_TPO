import asyncio
import os
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from app.application.ports.failure_injector import ConfigurableFailureInjector
from app.application.ports.messaging import Group, GroupCreate
from app.application.use_cases.problem_06_send_group_message import SendGroupMessageUseCase
from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.repositories.messaging import MongoMessagingStore
from app.infrastructure.persistence.redis.accounts import RedisAccountViews
from app.infrastructure.persistence.redis.messaging import ConversationLock, RedisMessagingViews
from tests.integration.support import Harness
from tests.integration.support import harness as harness

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1", reason="Requires real MongoDB/Redis"
)


def service(h: Harness) -> SendGroupMessageUseCase:
    return SendGroupMessageUseCase(
        MongoMessagingStore(h.resources.mongo_client[get_settings().mongodb_database]),
        RedisMessagingViews(h.resources.redis),
        ConversationLock(h.resources.redis),
    )


async def group(h: Harness, include_admin: bool = False) -> Group:
    return await service(h).create(
        h.user.id,
        GroupCreate(
            name="Datos", participant_ids=[h.moderator.id] + ([h.admin.id] if include_admin else [])
        ),
        str(uuid4()),
    )


async def test_group_permissions_validation_and_idempotency(harness: Harness) -> None:
    h = harness
    path = "/api/v1/messages/conversations"
    data = {"name": "Nuestro grupo", "participant_ids": [str(h.moderator.id)]}
    headers = {**h.headers(), "Idempotency-Key": "group-one"}
    first = await h.client.post(path, headers=headers, json=data)
    assert first.status_code == 201, first.text
    replay = await h.client.post(path, headers=headers, json=data)
    assert replay.json()["id"] == first.json()["id"]
    conflict = await h.client.post(path, headers=headers, json={**data, "name": "Distinto"})
    assert conflict.status_code == 409
    assert (await h.client.post(path, json=data)).status_code == 401
    assert (await h.client.post(path, headers=h.headers(), json=data)).status_code == 422
    for invalid in ([str(uuid4())], [str(h.user.id)]):
        response = await h.client.post(
            path,
            headers={**h.headers(), "Idempotency-Key": str(uuid4())},
            json={**data, "participant_ids": invalid},
        )
        assert response.status_code == 422
    group_id = first.json()["id"]
    assert (
        await h.client.get(path + f"/{group_id}", headers=h.headers(h.admin))
    ).status_code == 404
    search = await h.client.get("/api/v1/messages/participants?q=p7_", headers=h.headers())
    assert len(search.json()) == 2
    assert all("email" not in p and "password_hash" not in p for p in search.json())


async def test_concurrent_sends_retry_and_history_order(harness: Harness) -> None:
    h = harness
    g = await group(h)
    path = f"/api/v1/messages/conversations/{g.id}/messages"
    headers = {**h.headers(), "Idempotency-Key": "one-message"}
    results = await asyncio.gather(
        *[h.client.post(path, headers=headers, json={"text": "Único"}) for _ in range(8)]
    )
    assert all(r.status_code == 202 for r in results)
    assert len({r.json()["id"] for r in results}) == 1
    assert (
        await h.client.post(path, headers=headers, json={"text": "Distinto"})
    ).status_code == 409
    assert (
        await h.client.post(path, headers=h.headers(h.admin), json={"text": "Intruso"})
    ).status_code == 422
    forbidden = await h.client.post(
        path,
        headers={**h.headers(h.admin), "Idempotency-Key": "intruder"},
        json={"text": "Intruso"},
    )
    assert forbidden.status_code == 404
    sends = await asyncio.gather(
        *[service(h).send(g.id, h.user.id, str(i), str(uuid4())) for i in range(10)]
    )
    assert len({m.sequence for m in sends}) == 10
    history = (await h.client.get(path, headers=h.headers(h.moderator))).json()
    assert len(history["items"]) == 11
    assert history["items"][0]["sequence"] == max(m.sequence for m in sends)
    assert history["items"][0]["author_name"] == h.user.full_name
    assert "request_key" not in history["items"][0]
    spoof = await h.client.post(
        "/api/v1/problems/6/message",
        headers=headers,
        json={"conversation_id": str(g.id), "sender_id": str(h.admin.id), "text": "Impostor"},
    )
    assert spoof.status_code == 403


async def test_reads_are_monotonic_isolated_and_rebuild_redis(harness: Harness) -> None:
    h = harness
    svc = service(h)
    a, b = await group(h), await group(h)
    first = await svc.send(a.id, h.user.id, "Primero", str(uuid4()))
    second = await svc.send(a.id, h.user.id, "Segundo", str(uuid4()))
    other = await svc.send(b.id, h.user.id, "Otro grupo", str(uuid4()))
    assert await svc.views.unread(a.id, h.moderator.id) == 2
    assert await svc.views.unread(a.id, h.user.id) == 0
    assert await svc.read(a.id, h.moderator.id, first.id) == 1
    assert await svc.read(a.id, h.moderator.id, first.id) == 1
    assert await svc.read(a.id, h.moderator.id, second.id) == 0
    assert await svc.read(a.id, h.moderator.id, first.id) == 0
    assert await svc.views.unread(b.id, h.moderator.id) == 1
    response = await h.client.put(
        f"/api/v1/messages/conversations/{a.id}/read",
        headers=h.headers(h.moderator),
        json={"message_id": str(other.id)},
    )
    assert response.status_code == 422
    await svc.send(a.id, h.user.id, "Llega después", str(uuid4()))
    assert await svc.read(a.id, h.moderator.id, second.id) == 1
    # Simulate only this conversation's Redis data loss; never FLUSH shared Redis.
    await h.resources.redis.delete(RedisMessagingViews.key(a.id, h.moderator.id))
    listed = await svc.groups(h.moderator.id, None, 20)
    assert next(g for g in listed if g.id == a.id).unread == 1


@pytest.mark.parametrize("step", ["p6_after_persist", "p6_after_unread", "p6_after_notify"])
async def test_partial_failure_recovers_from_durable_outbox_without_duplicate_delivery(
    harness: Harness,
    step: str,
) -> None:
    h = harness
    g = await group(h, True)
    svc = service(h)
    await RedisAccountViews(h.resources.redis).heartbeat(h.moderator.id)
    await RedisAccountViews(h.resources.redis).heartbeat(h.admin.id)
    pubsub = h.resources.redis.pubsub()
    channel = f"user:{h.moderator.id}:messages:live"
    await pubsub.subscribe(channel)
    try:
        # Consume subscription acknowledgement before sending.
        await pubsub.get_message(timeout=1)
        message = await svc.send(
            g.id, h.user.id, "Siempre en historial", "retryable", ConfigurableFailureInjector(step)
        )
        assert message.delivery_status == "pending"
        assert (await svc.history(g.id, h.moderator.id, None, 30)).items[0].id == message.id
        # New service object: no in-memory flags or old request needed.
        await service(h).recover_pending()
        completed = await svc.status(message.id, h.moderator.id)
        assert completed.delivery_status == "completed" and completed.error is None
        assert await svc.views.unread(g.id, h.moderator.id) == 1
        assert await svc.views.unread(g.id, h.admin.id) == 1
        replay = await svc.send(g.id, h.user.id, "Siempre en historial", "retryable")
        assert replay.id == message.id
        assert len((await svc.history(g.id, h.user.id, None, 30)).items) == 1
        notices = []
        while event := await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1):
            notices.append(event)
        assert len(notices) == 1
    finally:
        await cast(Any, pubsub).aclose()


async def test_redis_failure_preserves_message_and_read_for_worker(harness: Harness) -> None:
    h = harness
    g = await group(h)
    real = RedisMessagingViews(h.resources.redis)

    class Unavailable(RedisMessagingViews):
        async def set_unread(self, group_id: UUID, actor: UUID, count: int) -> None:
            raise ConnectionError("Redis unavailable")

    svc = service(h)
    svc.views = Unavailable(h.resources.redis)
    message = await svc.send(g.id, h.user.id, "Mongo disponible", str(uuid4()))
    assert message.delivery_status == "pending"
    assert await svc.read(g.id, h.moderator.id, message.id) == 0
    stored = await svc.store.group(g.id)
    assert stored and stored.read_through[str(h.moderator.id)] == message.sequence
    await service(h).recover_pending()
    assert (await svc.status(message.id, h.user.id)).delivery_status == "completed"
    assert await real.unread(g.id, h.moderator.id) == 0


async def test_failure_before_insert_never_creates_unread(harness: Harness) -> None:
    h = harness
    g = await group(h)
    response = await h.client.post(
        f"/api/v1/messages/conversations/{g.id}/messages",
        headers={
            **h.headers(),
            "Idempotency-Key": "before-insert",
            "X-Fail-At-Step": "p6_before_persist",
        },
        json={"text": "No persistido"},
    )
    assert response.status_code == 500
    svc = service(h)
    assert not (await svc.history(g.id, h.user.id, None, 30)).items
    assert await svc.views.unread(g.id, h.moderator.id) == 0


async def test_suspension_denies_access_and_live_delivery_but_keeps_history(
    harness: Harness,
) -> None:
    h = harness
    g = await group(h)
    svc = service(h)
    db = h.resources.mongo_client[get_settings().mongodb_database]
    await RedisAccountViews(h.resources.redis).heartbeat(h.moderator.id)
    await db.users.update_one(
        {"_id": str(h.moderator.id)}, {"$set": {"account_status": "suspended"}}
    )
    await RedisAccountViews(h.resources.redis).block(h.moderator.id, uuid4())
    message = await svc.send(g.id, h.user.id, "Se conserva", str(uuid4()))
    assert await h.resources.redis.get(f"conversation:{g.id}:notified:{h.moderator.id}") is None
    response = await h.client.get(
        f"/api/v1/messages/conversations/{g.id}/messages", headers=h.headers(h.moderator)
    )
    assert response.status_code == 401
    await db.users.update_one({"_id": str(h.moderator.id)}, {"$set": {"account_status": "active"}})
    assert (await svc.history(g.id, h.moderator.id, None, 30)).items[0].id == message.id
    assert await svc.views.unread(g.id, h.moderator.id) == 1


async def test_keyset_history_survives_new_messages_and_cross_group_key_reuse(
    harness: Harness,
) -> None:
    h = harness
    svc = service(h)
    g = await group(h)
    for i in range(7):
        await svc.send(g.id, h.user.id, str(i), str(i))
    first = await svc.history(g.id, h.user.id, None, 3)
    await svc.send(g.id, h.user.id, "Nuevo", "new")
    second = await svc.history(g.id, h.user.id, first.next_before, 3)
    third = await svc.history(g.id, h.user.id, second.next_before, 3)
    ids = [m.id for page in (first, second, third) for m in page.items]
    assert len(ids) == len(set(ids)) == 7 and third.next_before is None
    other = await group(h)
    response = await h.client.post(
        f"/api/v1/messages/conversations/{other.id}/messages",
        headers={**h.headers(), "Idempotency-Key": "0"},
        json={"text": "0"},
    )
    assert response.status_code == 409
    assert not (await svc.history(other.id, h.user.id, None, 30)).items
