import asyncio
import logging

from app.application.ports import NoOpFailureInjector
from app.application.services import CompensationService, IdempotencyService
from app.application.services.account_processor import AccountProcessor
from app.application.services.follow_processor import FollowProcessor
from app.application.services.moderation_processor import ModerationProcessor
from app.application.use_cases.problem_05_interact_with_post import InteractWithPostUseCase
from app.application.use_cases.problem_06_send_group_message import SendGroupMessageUseCase
from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.client import create_mongo_client
from app.infrastructure.persistence.mongodb.repositories.accounts import MongoAccountStore
from app.infrastructure.persistence.mongodb.repositories.content_repositories import (
    MongoCommentRepository,
    MongoPostRepository,
    MongoReactionRepository,
)
from app.infrastructure.persistence.mongodb.repositories.follows import MongoFollowStore
from app.infrastructure.persistence.mongodb.repositories.identity import MongoUserRepository
from app.infrastructure.persistence.mongodb.repositories.messaging import MongoMessagingStore
from app.infrastructure.persistence.mongodb.repositories.moderation import MongoModerationRepository
from app.infrastructure.persistence.mongodb.repositories.operation_log import (
    MongoOperationLogRepository,
)
from app.infrastructure.persistence.neo4j.client import create_neo4j_driver
from app.infrastructure.persistence.neo4j.repositories import Neo4jSocialGraphRepository
from app.infrastructure.persistence.redis.accounts import RedisAccountViews
from app.infrastructure.persistence.redis.client import create_redis_client
from app.infrastructure.persistence.redis.follows import RedisFollowViews
from app.infrastructure.persistence.redis.messaging import ConversationLock, RedisMessagingViews
from app.infrastructure.persistence.redis.moderation import RedisModerationViews
from app.infrastructure.persistence.redis.reaction_lock import RedisReactionLock
from app.infrastructure.persistence.redis.repositories.operational_repositories import (
    RedisCounterRepository,
    RedisIdempotencyRepository,
    RedisNotificationRepository,
)

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    mongo = create_mongo_client(settings.mongodb_url)
    redis = create_redis_client(settings.redis_url)
    database = mongo[settings.mongodb_database]
    store = MongoModerationRepository(database)
    processor = ModerationProcessor(store, RedisModerationViews(redis))
    neo4j = create_neo4j_driver(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password.get_secret_value()
    )
    accounts = MongoAccountStore(database)
    account_processor = AccountProcessor(
        accounts, Neo4jSocialGraphRepository(neo4j), RedisAccountViews(redis)
    )
    follows = MongoFollowStore(database)
    follow_processor = FollowProcessor(
        follows, Neo4jSocialGraphRepository(neo4j), RedisFollowViews(redis)
    )
    operation_log = MongoOperationLogRepository(database)
    messaging_store = MongoMessagingStore(database)
    messaging = SendGroupMessageUseCase(
        messaging_store, RedisMessagingViews(redis), ConversationLock(redis)
    )
    interactions = InteractWithPostUseCase(
        MongoPostRepository(database),
        MongoReactionRepository(database),
        MongoCommentRepository(database),
        RedisCounterRepository(redis),
        RedisNotificationRepository(redis),
        CompensationService(operation_log, NoOpFailureInjector()),
        idempotency=IdempotencyService(RedisIdempotencyRepository(redis)),
        reaction_lock=RedisReactionLock(redis),
        users=MongoUserRepository(database),
        operation_log=operation_log,
    )
    try:
        await follows.ensure_indexes()
        await store.ensure_indexes()
        await accounts.ensure_indexes()
        await messaging_store.ensure_indexes()
        while True:
            try:
                # Resume interrupted P2 before applying other users' new transitions.
                for follow_job in await follows.pending():
                    await follow_processor.process(follow_job)
                for job in await store.pending():
                    await processor.process(job)
                for account_job in await accounts.pending():
                    await account_processor.process(account_job)
                # Proactively recover interrupted P5 operations (reactions, comments, idempotency)
                await interactions.recover_pending()
            except Exception:
                logger.exception("Moderation queue unavailable; persisted work will resume")
            try:
                await messaging.recover_pending()
            except Exception:
                logger.exception("P6 queue unavailable; persisted messages will resume")
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
