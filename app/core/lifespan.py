import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from neo4j import AsyncDriver
from pymongo import AsyncMongoClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.infrastructure.persistence.memory import InMemoryOperationLogRepository
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.neo4j.client import create_neo4j_driver
from app.infrastructure.persistence.postgres.session import (
    create_postgres_engine,
    create_session_factory,
)
from app.infrastructure.persistence.redis.client import create_redis_client

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Resources:
    postgres_engine: AsyncEngine
    postgres_sessions: async_sessionmaker[AsyncSession]
    mongo_client: AsyncMongoClient[dict[str, object]]
    redis: Redis
    neo4j: AsyncDriver
    operation_log: InMemoryOperationLogRepository


def build_lifespan(
    settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_postgres_engine(settings.postgres_dsn)
        mongo = create_mongo_client(settings.mongodb_url)
        redis = create_redis_client(settings.redis_url)
        neo4j = create_neo4j_driver(
            settings.neo4j_uri,
            settings.neo4j_user,
            settings.neo4j_password.get_secret_value(),
        )
        app.state.resources = Resources(
            postgres_engine=engine,
            postgres_sessions=create_session_factory(engine),
            mongo_client=mongo,
            redis=redis,
            neo4j=neo4j,
            operation_log=InMemoryOperationLogRepository(),
        )
        logger.info("Application resources initialized lazily")
        try:
            yield
        finally:
            await engine.dispose()
            await mongo.close()
            await redis.aclose()
            await neo4j.close()
            logger.info("Application resources closed")

    return lifespan

