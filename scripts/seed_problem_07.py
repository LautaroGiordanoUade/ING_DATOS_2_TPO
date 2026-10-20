"""Development-only fixtures. --reset replaces ONLY the four P7 fixture posts."""

import argparse
import asyncio
import json
import secrets
from uuid import UUID

from app.core.config import get_settings
from app.domain.entities import Comment, Post, Reaction, User
from app.domain.entities.models import ModerationStatus
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.mongodb.mappers.post_mapper import post_to_document
from app.infrastructure.persistence.mongodb.repositories.content_repositories import (
    MongoCommentRepository,
    MongoReactionRepository,
)
from app.infrastructure.persistence.mongodb.repositories.identity import MongoUserRepository
from app.infrastructure.persistence.mongodb.repositories.moderation import MongoModerationRepository
from app.infrastructure.persistence.redis.client import create_redis_client
from app.infrastructure.persistence.redis.keys import RedisKeys
from app.infrastructure.persistence.redis.publication_feeds import RedisPublicationFeeds
from app.infrastructure.security.password import PasswordHasher


async def seed(reset: bool) -> None:
    settings = get_settings()
    if settings.app_env != "development":
        raise RuntimeError("P7 fixtures require APP_ENV=development")
    mongo = create_mongo_client(settings.mongodb_url)
    redis = create_redis_client(settings.redis_url)
    database = mongo[settings.mongodb_database]
    password = secrets.token_urlsafe(18)
    digest = await asyncio.to_thread(PasswordHasher().hash, password)
    ids = [UUID(f"71000000-0000-0000-0000-{number:012d}") for number in range(1, 5)]
    users = [
        User(
            id=UUID(f"70000000-0000-0000-0000-{number:012d}"),
            username=f"p7_{role}",
            full_name=f"P7 {role}",
            email=f"p7_{role}@example.test",
            password_hash=digest,
            role="user" if role == "author" else role,
        )
        for number, role in enumerate(("user", "moderator", "admin", "author"), 1)
    ]
    try:
        await MongoUserRepository(database).ensure_indexes()
        await MongoModerationRepository(database).ensure_indexes()
        reactions, comments = MongoReactionRepository(database), MongoCommentRepository(database)
        await reactions.ensure_indexes()
        await comments.ensure_indexes()
        if reset:
            # A live worker must never race a fixture reset.
            active = await database["moderation_jobs"].count_documents(
                {"post_id": {"$in": [str(i) for i in ids]}, "active": True}
            )
            if active:
                raise RuntimeError(
                    "P7 fixture operations are active; finish/recover them before --reset"
                )
            for collection in (
                "moderation_jobs",
                "moderation_reports",
                "moderation_history",
                "reactions",
                "comments",
            ):
                await database[collection].delete_many({"post_id": {"$in": [str(i) for i in ids]}})
        for user in users:
            existing = await MongoUserRepository(database).get(user.id)
            if existing is None:
                await MongoUserRepository(database).create(user)
            else:
                await database["users"].update_one(
                    {"_id": str(user.id)}, {"$set": {"password_hash": digest}}
                )
        feeds = RedisPublicationFeeds(redis)
        for number, post_id in enumerate(ids, 1):
            existing_post = await database["posts"].find_one({"_id": str(post_id)})
            if existing_post is not None and not reset:
                continue
            post = Post(
                id=post_id,
                user_id=users[-1].id,
                text=f"P7 fixture {number}",
                interests=("data",),
                moderation_status=ModerationStatus.APPROVED,
            )
            doc = post_to_document(post)
            doc["publication_state"] = "published"
            await database["posts"].replace_one({"_id": str(post_id)}, doc, upsert=True)
            await redis.delete(f"moderation:{post_id}:hidden")
            await feeds.stage_batch((users[0].id,), post_id, post.published_at.timestamp())
            await feeds.commit(post_id)
            for actor in users[:2]:
                await reactions.upsert(Reaction(post_id=post_id, user_id=actor.id, kind="like"))
            await comments.create(
                Comment(post_id=post_id, user_id=users[0].id, text="P7 visible comment")
            )
            for namespace, value in (("post_reactions", 2), ("post_comments", 1)):
                key = RedisKeys.counter(namespace, post_id)
                await redis.set(key, value)
                await redis.delete(key + ":moderation_saved")
        print(
            json.dumps(
                {
                    "password": password,
                    "users": [
                        {"id": str(user.id), "username": user.username, "role": user.role}
                        for user in users
                    ],
                    "posts": dict(
                        zip(("hide", "reject", "revert", "concurrency"), map(str, ids), strict=True)
                    ),
                    "swagger": "http://localhost:8000/docs",
                },
                indent=2,
            )
        )
    finally:
        await mongo.close()
        await redis.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true")
    asyncio.run(seed(parser.parse_args().reset))
