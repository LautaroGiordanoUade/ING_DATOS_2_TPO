from dataclasses import dataclass

from app.api.dependencies.databases import PostgresSessionDep, ResourcesDep
from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.database import get_mongo_database
from app.infrastructure.persistence.mongodb.repositories import (
    MongoCommentRepository,
    MongoConversationRepository,
    MongoMessageRepository,
    MongoPostRepository,
    MongoReactionRepository,
)
from app.infrastructure.persistence.neo4j.repositories import Neo4jSocialGraphRepository
from app.infrastructure.persistence.postgres.repositories import (
    PostgresModerationRepository,
    PostgresUserRepository,
)
from app.infrastructure.persistence.redis.repositories import (
    RedisCounterRepository,
    RedisFeedRepository,
    RedisNotificationRepository,
)


@dataclass(slots=True)
class RepositoryContainer:
    users: PostgresUserRepository
    moderation: PostgresModerationRepository
    posts: MongoPostRepository
    comments: MongoCommentRepository
    reactions: MongoReactionRepository
    conversations: MongoConversationRepository
    messages: MongoMessageRepository
    graph: Neo4jSocialGraphRepository
    feeds: RedisFeedRepository
    counters: RedisCounterRepository
    notifications: RedisNotificationRepository


def get_repositories(
    resources: ResourcesDep,
    session: PostgresSessionDep,
) -> RepositoryContainer:
    settings = get_settings()
    mongo_database = get_mongo_database(resources.mongo_client, settings.mongodb_database)
    return RepositoryContainer(
        users=PostgresUserRepository(session),
        moderation=PostgresModerationRepository(session),
        posts=MongoPostRepository(mongo_database),
        comments=MongoCommentRepository(mongo_database),
        reactions=MongoReactionRepository(mongo_database),
        conversations=MongoConversationRepository(mongo_database),
        messages=MongoMessageRepository(mongo_database),
        graph=Neo4jSocialGraphRepository(resources.neo4j),
        feeds=RedisFeedRepository(resources.redis),
        counters=RedisCounterRepository(resources.redis),
        notifications=RedisNotificationRepository(resources.redis),
    )

