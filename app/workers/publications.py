import asyncio
import fcntl
import logging

from app.application.services.publication_processor import PublicationProcessor
from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.mongodb.repositories.publication_jobs import (
    MongoPublicationJobs,
)
from app.infrastructure.persistence.neo4j.client import create_neo4j_driver
from app.infrastructure.persistence.neo4j.repositories import Neo4jSocialGraphRepository
from app.infrastructure.persistence.redis.client import create_redis_client
from app.infrastructure.persistence.redis.publication_feeds import RedisPublicationFeeds

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    mongo = create_mongo_client(settings.mongodb_url)
    redis = create_redis_client(settings.redis_url)
    neo4j = create_neo4j_driver(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password.get_secret_value()
    )
    jobs = MongoPublicationJobs(mongo[settings.mongodb_database])
    processor = PublicationProcessor(
        jobs, Neo4jSocialGraphRepository(neo4j), RedisPublicationFeeds(redis)
    )
    try:
        await jobs.ensure_indexes()
        async with neo4j.session() as session:
            await session.run(
                "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE"
            )
        while True:
            try:
                pending = await jobs.pending()
                for job in pending:
                    try:
                        await processor.process(job)
                    except Exception:
                        logger.exception(
                            "Publication will be retried: %s", job.operation.operation_id
                        )
                await asyncio.sleep(0.5)
            except Exception:
                logger.exception("Publication queue unavailable; retrying")
                await asyncio.sleep(2)
    finally:
        await mongo.close()
        await redis.aclose()
        await neo4j.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # The shared local volume permits one consumer, even if accidentally scaled.
    # The OS releases flock automatically on SIGKILL; no orphan lease survives.
    with open("/home/appuser/publication-worker/consumer.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        asyncio.run(main())
