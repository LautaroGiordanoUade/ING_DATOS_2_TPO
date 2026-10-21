import asyncio
import logging

from app.application.services.account_processor import AccountProcessor
from app.application.services.moderation_processor import ModerationProcessor
from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.mongodb.repositories.accounts import MongoAccountStore
from app.infrastructure.persistence.mongodb.repositories.moderation import MongoModerationRepository
from app.infrastructure.persistence.neo4j.client import create_neo4j_driver
from app.infrastructure.persistence.neo4j.repositories import Neo4jSocialGraphRepository
from app.infrastructure.persistence.redis.accounts import RedisAccountViews
from app.infrastructure.persistence.redis.client import create_redis_client
from app.infrastructure.persistence.redis.moderation import RedisModerationViews

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    mongo = create_mongo_client(settings.mongodb_url)
    redis = create_redis_client(settings.redis_url)
    store = MongoModerationRepository(mongo[settings.mongodb_database])
    processor = ModerationProcessor(store, RedisModerationViews(redis))
    neo4j = create_neo4j_driver(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password.get_secret_value()
    )
    accounts = MongoAccountStore(mongo[settings.mongodb_database])
    account_processor = AccountProcessor(
        accounts, Neo4jSocialGraphRepository(neo4j), RedisAccountViews(redis)
    )
    try:
        await store.ensure_indexes()
        await accounts.ensure_indexes()
        while True:
            try:
                for job in await store.pending():
                    await processor.process(job)
                for account_job in await accounts.pending():
                    await account_processor.process(account_job)
            except Exception:
                logger.exception("Moderation queue unavailable; persisted work will resume")
            await asyncio.sleep(0.5)
    finally:
        await mongo.close()
        await redis.aclose()
        await neo4j.close()


if __name__ == "__main__":
    import fcntl

    logging.basicConfig(level=logging.INFO)
    with open("/home/appuser/moderation-worker/consumer.lock", "w") as lock:
        # Same host/volume deployment contract as P1; released by the OS on crash.
        fcntl.flock(lock, fcntl.LOCK_EX)
        asyncio.run(main())
