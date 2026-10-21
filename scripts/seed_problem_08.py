"""Create/reset only P8 development fixtures in the three existing engines."""

import asyncio
import json
import secrets
from dataclasses import asdict
from uuid import UUID

from app.core.config import get_settings
from app.domain.entities import Comment, Conversation, Post, Reaction, User
from app.domain.entities.models import ModerationStatus
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.mongodb.indexes import ensure_mongo_indexes
from app.infrastructure.persistence.mongodb.mappers.post_mapper import post_to_document
from app.infrastructure.persistence.mongodb.repositories.content_repositories import (
    MongoCommentRepository,
    MongoReactionRepository,
)
from app.infrastructure.persistence.neo4j.client import create_neo4j_driver
from app.infrastructure.persistence.redis.accounts import RedisAccountViews
from app.infrastructure.persistence.redis.client import create_redis_client
from app.infrastructure.persistence.redis.moderation import RedisModerationViews
from app.infrastructure.persistence.redis.publication_feeds import RedisPublicationFeeds
from app.infrastructure.persistence.redis.repositories.operational_repositories import (
    RedisCounterRepository,
)
from app.infrastructure.security.password import PasswordHasher


async def main() -> None:
    settings = get_settings()
    if settings.app_env != "development":
        raise RuntimeError("P8 fixtures require APP_ENV=development")
    mongo = create_mongo_client(settings.mongodb_url)
    redis = create_redis_client(settings.redis_url)
    graph = create_neo4j_driver(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password.get_secret_value()
    )
    database = mongo[settings.mongodb_database]
    password = secrets.token_urlsafe(18)
    digest = await asyncio.to_thread(PasswordHasher().hash, password)
    users = [
        User(
            id=UUID(f"80000000-0000-0000-0000-{i:012d}"),
            username=f"p8_{name}",
            full_name=f"P8 {name}",
            email=f"p8_{name}@example.test",
            password_hash=digest,
            role=name if name in ("moderator", "admin") else "user",
        )
        for i, name in enumerate(("target", "moderator", "admin", "observer"), 1)
    ]
    post_ids = [UUID(f"81000000-0000-0000-0000-{i:012d}") for i in range(1, 4)]
    ids = [str(user.id) for user in users]
    try:
        await ensure_mongo_indexes(database)
        if await database["account_jobs"].count_documents(
            {"user_id": {"$in": ids}, "active": True}
        ):
            raise RuntimeError(
                "P8 operations active; finish/recover them before resetting fixtures"
            )
        if await database["moderation_jobs"].count_documents(
            {"post_id": {"$in": [str(p) for p in post_ids]}, "active": True}
        ):
            raise RuntimeError("P7 operations active on P8 fixtures")
        operations = [
            str(doc["_id"])
            async for doc in database["account_jobs"].find({"user_id": {"$in": ids}})
        ]
        await database["account_post_snapshots"].delete_many({"operation_id": {"$in": operations}})
        for collection in ("account_jobs", "account_history"):
            await database[collection].delete_many({"user_id": {"$in": ids}})
        for collection in ("moderation_jobs", "moderation_reports", "moderation_history"):
            await database[collection].delete_many({"post_id": {"$in": [str(p) for p in post_ids]}})
        for collection in ("reactions", "comments"):
            await database[collection].delete_many({"post_id": {"$in": [str(p) for p in post_ids]}})
        for identifier in ids + [str(p) for p in post_ids]:
            keys = [key async for key in redis.scan_iter(match=f"*{identifier}*")]
            if keys:
                await redis.delete(*keys)
        for user in users:
            doc = asdict(user)
            doc["_id"] = str(doc.pop("id"))
            await database["users"].replace_one({"_id": str(user.id)}, doc, upsert=True)
        posts = [
            Post(
                id=post_id,
                user_id=users[0 if i < 2 else 3].id,
                text=f"P8 fixture {i + 1}",
                interests=("data",),
                moderation_status=ModerationStatus.HIDDEN if i == 1 else ModerationStatus.APPROVED,
            )
            for i, post_id in enumerate(post_ids)
        ]
        feeds = RedisPublicationFeeds(redis)
        counters = RedisCounterRepository(redis)
        for i, post in enumerate(posts):
            doc = post_to_document(post)
            doc["publication_state"] = "published"
            await database["posts"].replace_one({"_id": str(post.id)}, doc, upsert=True)
            await feeds.stage_batch(
                (users[0].id,) if i == 2 else (users[1].id, users[3].id), post.id, 100 + i
            )
            await feeds.commit(post.id)
            for actor in users[1:3]:
                await MongoReactionRepository(database).upsert(
                    Reaction(post_id=post.id, user_id=actor.id, kind="like")
                )
            await MongoCommentRepository(database).create(
                Comment(post_id=post.id, user_id=users[3].id, text="P8 real fixture comment")
            )
            await counters.increment("post_reactions", post.id, 2)
            await counters.increment("post_comments", post.id, 1)
            if i == 1:
                views = RedisModerationViews(redis)
                snapshot = await views.snapshot(post.id)
                await views.hide(post.id)
                await views.remove_feeds(post.id, snapshot)
        conversation = Conversation(
            id=UUID("82000000-0000-0000-0000-000000000001"),
            participant_ids=(users[0].id, users[3].id),
        )
        await database["conversations"].replace_one(
            {"_id": str(conversation.id)},
            {
                "_id": str(conversation.id),
                "participant_ids": [str(p) for p in conversation.participant_ids],
                "created_at": conversation.created_at,
            },
            upsert=True,
        )
        async with graph.session() as session:
            result = await session.run("MATCH (u:User) WHERE u.id IN $ids DETACH DELETE u", ids=ids)
            await result.consume()
            result = await session.run(
                """
                CREATE (u:User {id:$target,account_status:'active'}),
                       (m:User {id:$moderator,account_status:'active'}),
                       (a:User {id:$admin,account_status:'active'}),
                       (o:User {id:$observer,account_status:'active'}),
                       (m)-[:FOLLOWS {status:'accepted'}]->(o),
                       (o)-[:FOLLOWS {status:'accepted'}]->(u)
            """,
                target=ids[0],
                moderator=ids[1],
                admin=ids[2],
                observer=ids[3],
            )
            await result.consume()
        await RedisAccountViews(redis).heartbeat(users[0].id)
        print(
            json.dumps(
                {
                    "password": password,
                    "users": [
                        {"id": str(u.id), "username": u.username, "role": u.role} for u in users
                    ],
                    "posts": list(map(str, post_ids)),
                    "conversation_id": str(conversation.id),
                },
                indent=2,
            )
        )
    finally:
        await mongo.close()
        await redis.aclose()
        await graph.close()


if __name__ == "__main__":
    asyncio.run(main())
