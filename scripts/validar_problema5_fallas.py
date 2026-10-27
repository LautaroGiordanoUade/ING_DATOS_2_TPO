"""Controlled failure and concurrency checks against real MongoDB and Redis."""

import asyncio
import json
from uuid import uuid4

from pymongo import AsyncMongoClient
from redis.asyncio import Redis

from app.application.ports import NoOpFailureInjector
from app.application.services import CompensationService
from app.application.use_cases.problem_05_interact_with_post import InteractWithPostUseCase
from app.core.config import get_settings
from app.domain.entities import Post, Reaction
from app.domain.entities.models import ModerationStatus
from app.infrastructure.persistence.mongodb.mappers.post_mapper import post_to_document
from app.infrastructure.persistence.mongodb.repositories.content_repositories import (
    MongoCommentRepository,
    MongoPostRepository,
    MongoReactionRepository,
)
from app.infrastructure.persistence.mongodb.repositories.operation_log import (
    MongoOperationLogRepository,
)
from app.infrastructure.persistence.redis.reaction_lock import RedisReactionLock
from app.infrastructure.persistence.redis.repositories.operational_repositories import (
    RedisCounterRepository,
    RedisNotificationRepository,
)


async def main():
    s = get_settings()
    mongo = AsyncMongoClient(s.mongodb_url)
    db = mongo[s.mongodb_database]
    redis = Redis.from_url(s.redis_url)
    author, actor, post = uuid4(), uuid4(), uuid4()
    await db.posts.insert_one(
        post_to_document(
            Post(
                id=post,
                user_id=author,
                text="Validacion fallo parcial",
                moderation_status=ModerationStatus.APPROVED,
            )
        )
    )

    class FailPublishClient:
        def __getattr__(self, name):
            return getattr(redis, name)

        async def publish(self, *args, **kwargs):
            raise ConnectionError("Falla controlada despues de HSET y antes de PUBLISH")

    def use_case(reactions, notifications):
        return InteractWithPostUseCase(
            MongoPostRepository(db),
            reactions,
            MongoCommentRepository(db),
            RedisCounterRepository(redis),
            notifications,
            CompensationService(MongoOperationLogRepository(db), NoOpFailureInjector()),
            reaction_lock=RedisReactionLock(redis),
        )

    uc = use_case(MongoReactionRepository(db), RedisNotificationRepository(FailPublishClient()))
    try:
        await uc.react(Reaction(post_id=post, user_id=actor, kind="like"))
    except ConnectionError:
        pass
    result = {
        "test": "Fallo dentro de notificacion (HSET exitoso, PUBLISH falla)",
        "reactions_mongo": await db.reactions.count_documents({"post_id": str(post)}),
        "counter_redis": int(await redis.get(f"post_reactions:{post}:count") or 0),
        "notifications_remaining": await redis.hlen(f"user:{author}:notifications"),
    }
    result["ok"] = all(
        result[key] == 0
        for key in (
            "reactions_mongo",
            "counter_redis",
            "notifications_remaining",
        )
    )
    assert result["ok"], result
    print(json.dumps(result), flush=True)
    # Force a valid overlapping schedule: create writes Mongo, delete finishes, create resumes.
    created = asyncio.Event()
    resume = asyncio.Event()

    class PausedReactions:
        def __init__(self):
            self.repo = MongoReactionRepository(db)

        def __getattr__(self, name):
            return getattr(self.repo, name)

        async def upsert(self, reaction):
            previous = await self.repo.upsert(reaction)
            created.set()
            await resume.wait()
            return previous

        async def delete_for_user(self, *args):
            return await self.repo.delete_for_user(*args)

    slow = use_case(PausedReactions(), RedisNotificationRepository(redis))
    normal = use_case(MongoReactionRepository(db), RedisNotificationRepository(redis))
    task = asyncio.create_task(slow.react(Reaction(post_id=post, user_id=actor, kind="like")))
    await asyncio.wait_for(created.wait(), timeout=5)
    removal = asyncio.create_task(normal.remove_reaction(post, actor))
    await asyncio.sleep(0.1)
    assert not removal.done(), "El borrado debe esperar el bloqueo"
    resume.set()
    await asyncio.gather(task, removal)
    docs = await db.reactions.count_documents({"post_id": str(post)})
    count = int(await redis.get(f"post_reactions:{post}:count") or 0)
    assert (docs, count) == (0, 0), (docs, count)
    print(
        json.dumps(
            {
                "test": "Crear y borrar concurrentemente con orden controlado",
                "ok": docs == count,
                "reactions_mongo": docs,
                "counter_redis": count,
            }
        ),
        flush=True,
    )
    print(
        "TEST_DATA "
        + json.dumps({"post_id": str(post), "author_id": str(author), "actor_id": str(actor)}),
        flush=True,
    )
    await mongo.close()
    await redis.aclose()


asyncio.run(main())
