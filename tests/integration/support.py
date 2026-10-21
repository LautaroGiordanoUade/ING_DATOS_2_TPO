"""Real MongoDB/Redis tests, isolated database and UUID keys; no repository substitutes."""

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.application.services.moderation_job import ModerationJob
from app.application.services.moderation_processor import ModerationProcessor
from app.core.config import get_settings
from app.core.lifespan import Resources
from app.domain.counter_names import POST_COMMENTS, POST_REACTIONS
from app.domain.entities import Post, User
from app.domain.entities.models import ModerationStatus
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.mongodb.indexes import ensure_mongo_indexes
from app.infrastructure.persistence.mongodb.repositories.content_repositories import (
    MongoPostRepository,
)
from app.infrastructure.persistence.mongodb.repositories.identity import MongoUserRepository
from app.infrastructure.persistence.mongodb.repositories.moderation import MongoModerationRepository
from app.infrastructure.persistence.mongodb.repositories.operation_log import (
    MongoOperationLogRepository,
)
from app.infrastructure.persistence.neo4j.client import create_neo4j_driver
from app.infrastructure.persistence.redis.client import create_redis_client
from app.infrastructure.persistence.redis.moderation import RedisModerationViews
from app.infrastructure.persistence.redis.publication_feeds import RedisPublicationFeeds
from app.infrastructure.persistence.redis.repositories.operational_repositories import (
    RedisCounterRepository,
)
from app.infrastructure.security.password import PasswordHasher
from app.infrastructure.security.tokens import TokenService
from app.main import create_app

_PASSWORD = "integration-password-07"
_DIGEST = PasswordHasher().hash(_PASSWORD)


@dataclass
class Harness:
    app: FastAPI
    client: httpx.AsyncClient
    resources: Resources
    store: MongoModerationRepository
    views: RedisModerationViews
    posts: MongoPostRepository
    user: User
    moderator: User
    admin: User
    post: Post

    def headers(self, actor: User | None = None) -> dict[str, str]:
        return {
            "Authorization": "Bearer " + TokenService().create_access_token((actor or self.user).id)
        }

    async def report(self, actor: User | None = None) -> UUID:
        response = await self.client.post(
            "/api/v1/moderation/reports",
            headers=self.headers(actor),
            json={"post_id": str(self.post.id), "reason": "spam", "description": "P7 test"},
        )
        assert response.status_code == 201, response.text
        return UUID(response.json()["id"])

    async def decision(self, report_id: UUID, action: str = "hide", **kwargs: Any) -> ModerationJob:
        response = await self.client.post(
            f"/api/v1/moderation/reports/{report_id}/decision",
            headers={**self.headers(self.moderator), **kwargs},
            json={"decision": action, "reason": "Confirmed test"},
        )
        assert response.status_code == 202, response.text
        return ModerationJob.model_validate(response.json())

    async def run(self, job: ModerationJob) -> ModerationJob:
        # Reconstruct repository and processor each time, as after a worker restart.
        store = MongoModerationRepository(
            self.resources.mongo_client[get_settings().mongodb_database]
        )
        current = await store.get_job(job.operation_id)
        assert current is not None
        await ModerationProcessor(store, RedisModerationViews(self.resources.redis)).process(
            current
        )
        result = await store.get_job(job.operation_id)
        assert result is not None
        return result

    async def counts(self) -> dict[str, int]:
        repository = RedisCounterRepository(self.resources.redis)
        return {
            name: (await repository.get_many(name, (self.post.id,)))[self.post.id]
            for name in (POST_REACTIONS, POST_COMMENTS)
        }


@pytest.fixture
async def harness(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Harness]:
    database_name = "test_p7_" + uuid4().hex
    monkeypatch.setenv("MONGODB_DATABASE", database_name)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD", "local_dev_password"))
    get_settings.cache_clear()
    settings = get_settings()
    # Same local engines; avoid a Windows IPv6 connection fallback on every fixture.
    settings.mongodb_url = settings.mongodb_url.replace("://localhost:", "://127.0.0.1:")
    settings.redis_url = settings.redis_url.replace("://localhost:", "://127.0.0.1:")
    settings.neo4j_uri = settings.neo4j_uri.replace("://localhost:", "://127.0.0.1:")
    mongo = create_mongo_client(settings.mongodb_url)
    redis = create_redis_client(settings.redis_url)
    neo4j = create_neo4j_driver(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password.get_secret_value()
    )
    database = mongo[database_name]
    resources = Resources(mongo, redis, neo4j, MongoOperationLogRepository(database))
    app = create_app()
    app.state.resources = resources
    await ensure_mongo_indexes(database)
    users = MongoUserRepository(database)
    user, moderator, admin = [
        User(
            username="p7_" + role,
            full_name=role,
            email=role + "@p7.test",
            password_hash=_DIGEST,
            role=role,
        )
        for role in ("user", "moderator", "admin")
    ]
    for actor in (user, moderator, admin):
        await users.create(actor)
    posts = MongoPostRepository(database)
    post = Post(
        user_id=admin.id, text="P7 real content", moderation_status=ModerationStatus.APPROVED
    )
    await posts.create(post)
    feed = RedisPublicationFeeds(redis)
    await feed.stage_batch((user.id, moderator.id), post.id, 123.5)
    await feed.commit(post.id)
    counters = RedisCounterRepository(redis)
    await counters.increment(POST_REACTIONS, post.id, 2)
    await counters.increment(POST_COMMENTS, post.id, 3)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield Harness(
                app,
                client,
                resources,
                MongoModerationRepository(database),
                RedisModerationViews(redis),
                posts,
                user,
                moderator,
                admin,
                post,
            )
    finally:
        ids = [str(actor.id) for actor in (user, moderator, admin)]
        ids += [str(doc["_id"]) async for doc in database["posts"].find({})]
        for identifier in ids:
            keys = [key async for key in redis.scan_iter(match=f"*{identifier}*")]
            if keys:
                await redis.delete(*keys)
        assert database_name.startswith("test_p7_")
        await mongo.drop_database(database_name)
        await mongo.close()
        await redis.aclose()
        await neo4j.close()
        get_settings.cache_clear()
