from pymongo.asynchronous.database import AsyncDatabase

from app.infrastructure.persistence.mongodb.repositories import (
    MongoCommentRepository,
    MongoReactionRepository,
)


async def ensure_mongo_indexes(database: AsyncDatabase[dict[str, object]]) -> None:
    """Crea los índices de MongoDB. Es seguro ejecutarlo en cada arranque."""
    await MongoReactionRepository(database).ensure_indexes()
    await MongoCommentRepository(database).ensure_indexes()
    from app.infrastructure.persistence.mongodb.repositories.identity import MongoUserRepository
    from app.infrastructure.persistence.mongodb.repositories.moderation import (
        MongoModerationRepository,
    )

    await MongoUserRepository(database).ensure_indexes()
    await MongoModerationRepository(database).ensure_indexes()

    from app.infrastructure.persistence.mongodb.repositories.accounts import MongoAccountStore

    await MongoAccountStore(database).ensure_indexes()

    from app.infrastructure.persistence.mongodb.repositories.follows import MongoFollowStore

    await MongoFollowStore(database).ensure_indexes()

    from app.infrastructure.persistence.mongodb.repositories.messaging import MongoMessagingStore

    await MongoMessagingStore(database).ensure_indexes()
