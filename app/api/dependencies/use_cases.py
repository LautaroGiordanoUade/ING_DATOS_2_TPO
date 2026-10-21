from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.api.dependencies.databases import ResourcesDep
from app.api.dependencies.repositories import RepositoryContainer, get_repositories
from app.application.ports import (
    ConfigurableFailureInjector,
    FailureInjector,
    NoOpFailureInjector,
)
from app.application.services import CompensationService, IdempotencyService
from app.application.use_cases import (
    FollowUserUseCase,
    GetFeedUseCase,
    InteractWithPostUseCase,
    ModeratePostUseCase,
    PublishContentUseCase,
    SendGroupMessageUseCase,
    SocialRecommendationsUseCase,
    SuspendAndTraceUserUseCase,
)
from app.core.config import get_settings
from app.infrastructure.persistence.mongodb.repositories.accounts import MongoAccountStore
from app.infrastructure.persistence.mongodb.repositories.publication_jobs import (
    MongoPublicationJobs,
)
from app.infrastructure.persistence.redis.accounts import RedisAccountViews
from app.infrastructure.persistence.redis.moderation import RedisModerationViews
from app.infrastructure.persistence.redis.reaction_lock import RedisReactionLock
from app.infrastructure.persistence.redis.repositories.operational_repositories import (
    RedisIdempotencyRepository,
)

RepositoriesDep = Annotated[RepositoryContainer, Depends(get_repositories)]


def get_failure_injector(
    x_fail_at_step: Annotated[str | None, Header()] = None,
) -> FailureInjector:
    settings = get_settings()
    if x_fail_at_step is None:
        return NoOpFailureInjector()
    if settings.app_env != "development":
        raise HTTPException(status_code=400, detail="Failure injection is development-only")
    return ConfigurableFailureInjector(x_fail_at_step)


FailureInjectorDep = Annotated[FailureInjector, Depends(get_failure_injector)]


def get_publish_use_case(resources: ResourcesDep) -> PublishContentUseCase:
    database = resources.mongo_client[get_settings().mongodb_database]
    return PublishContentUseCase(MongoPublicationJobs(database))


def get_follow_use_case(
    repositories: RepositoriesDep,
    resources: ResourcesDep,
    failure_injector: FailureInjectorDep,
) -> FollowUserUseCase:
    return FollowUserUseCase(
        repositories.users,
        repositories.graph,
        repositories.counters,
        repositories.feeds,
        CompensationService(resources.operation_log, failure_injector),
    )


def get_feed_use_case(repositories: RepositoriesDep) -> GetFeedUseCase:
    return GetFeedUseCase(repositories.feeds, repositories.posts, repositories.counters)


def get_recommendations_use_case(
    repositories: RepositoriesDep,
) -> SocialRecommendationsUseCase:
    return SocialRecommendationsUseCase(repositories.graph, repositories.users)


def get_interaction_use_case(
    repositories: RepositoriesDep,
    resources: ResourcesDep,
    failure_injector: FailureInjectorDep,
) -> InteractWithPostUseCase:
    return InteractWithPostUseCase(
        repositories.posts,
        repositories.reactions,
        repositories.comments,
        repositories.counters,
        repositories.notifications,
        CompensationService(resources.operation_log, failure_injector),
        idempotency=IdempotencyService(RedisIdempotencyRepository(resources.redis)),
        reaction_lock=RedisReactionLock(resources.redis),
        users=repositories.users,
    )


def get_message_use_case(
    repositories: RepositoriesDep,
    resources: ResourcesDep,
    failure_injector: FailureInjectorDep,
) -> SendGroupMessageUseCase:
    return SendGroupMessageUseCase(
        repositories.conversations,
        repositories.messages,
        repositories.counters,
        repositories.notifications,
        CompensationService(resources.operation_log, failure_injector),
    )


def get_moderation_use_case(
    repositories: RepositoriesDep,
    resources: ResourcesDep,
    failure_injector: FailureInjectorDep,
) -> ModeratePostUseCase:
    return ModeratePostUseCase(repositories.moderation, RedisModerationViews(resources.redis))


def get_suspend_trace_use_case(
    repositories: RepositoriesDep,
    resources: ResourcesDep,
    failure_injector: FailureInjectorDep,
) -> SuspendAndTraceUserUseCase:
    database = resources.mongo_client[get_settings().mongodb_database]
    return SuspendAndTraceUserUseCase(
        MongoAccountStore(database),
        repositories.graph,
        RedisAccountViews(resources.redis),
        repositories.posts,
        repositories.conversations,
    )
