from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.dependencies.auth import CurrentUserDep, ModeratorDep
from app.api.dependencies.databases import ResourcesDep
from app.api.dependencies.demo import DemoModeDep
from app.api.dependencies.use_cases import (
    RepositoriesDep,
    get_interaction_use_case,
    get_message_use_case,
    get_moderation_use_case,
    get_publish_use_case,
    get_recommendations_use_case,
    get_suspend_trace_use_case,
)
from app.api.v1.routers.feeds import get_user_feed
from app.api.v1.routers.social import approve_follow, create_follow, delete_follow, follow_operation
from app.application.services.follow_job import FollowJob
from app.application.use_cases import (
    InteractWithPostUseCase,
    ModeratePostUseCase,
    PublishContentUseCase,
    SendGroupMessageUseCase,
    SocialRecommendationsUseCase,
    SuspendAndTraceUserUseCase,
)
from app.core.config import get_settings
from app.core.exceptions import ResourceNotFoundError
from app.domain.entities import Comment, Message, Post, Reaction
from app.infrastructure.persistence.mongodb.repositories.publication_jobs import (
    MongoPublicationJobs,
)
from app.infrastructure.persistence.redis.publication_feeds import RedisPublicationFeeds
from app.schemas.models import (
    CommentCreate,
    FeedResponse,
    MessageCreate,
    ModerationRequest,
    MutualFriendsRequest,
    OperationDetailResponse,
    OperationResponse,
    PostCreate,
    PublicationResponse,
    ReactionCreate,
    ReactionRemove,
    SuspensionRequest,
    UserTraceResponse,
)

router = APIRouter()


@router.get("/operations/{operation_id}", response_model=OperationDetailResponse)
async def get_operation(operation_id: UUID, resources: ResourcesDep) -> OperationDetailResponse:
    database = resources.mongo_client[get_settings().mongodb_database]
    publication = await MongoPublicationJobs(database).get(operation_id)
    operation = (
        publication.operation if publication else await resources.operation_log.get(operation_id)
    )
    if operation is None:
        raise ResourceNotFoundError("Operación no encontrada")
    return OperationDetailResponse(
        post_id=publication.post.id if publication else None,
        operation_id=operation.operation_id,
        operation_type=operation.operation_type,
        status=operation.status.value,
        current_step=operation.current_step,
        completed_steps=operation.completed_steps,
        error=operation.error,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
    )


@router.post("/1/publish", response_model=PublicationResponse, status_code=status.HTTP_202_ACCEPTED)
async def publish(
    payload: PostCreate,
    use_case: Annotated[PublishContentUseCase, Depends(get_publish_use_case)],
    resources: ResourcesDep,
    demo_mode: DemoModeDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    x_fail_at_step: Annotated[str | None, Header(alias="X-Fail-At-Step")] = None,
) -> PublicationResponse:
    if x_fail_at_step is not None and get_settings().app_env != "development":
        from app.core.exceptions import InvalidOperationError

        raise InvalidOperationError("Failure injection is development-only")
    post = Post(
        user_id=payload.user_id,
        text=payload.text,
        media=tuple(payload.media),
        interests=tuple(payload.interests),
        visibility=payload.visibility,
    )
    job = await use_case.execute(post, idempotency_key, x_fail_at_step)
    return PublicationResponse(
        operation_id=job.operation.operation_id,
        status=job.operation.status.value,
        post_id=job.post.id,
    )


@router.get("/1/feed-preview/{user_id}")
async def publication_feed_preview(
    user_id: UUID, resources: ResourcesDep, repositories: RepositoriesDep
) -> dict[str, object]:
    """Visible P1 publication IDs only. Personalized feed belongs to problem 3."""
    ids = await RedisPublicationFeeds(resources.redis).visible_ids(user_id)
    posts = await repositories.posts.get_many(ids)
    return {"user_id": str(user_id), "post_ids": [str(post.id) for post in posts]}


router.add_api_route(
    "/2/follow", create_follow, methods=["POST"], response_model=FollowJob, status_code=202
)
router.add_api_route(
    "/2/follow", delete_follow, methods=["DELETE"], response_model=FollowJob, status_code=202
)
router.add_api_route(
    "/2/approve", approve_follow, methods=["POST"], response_model=FollowJob, status_code=202
)
router.add_api_route(
    "/2/operations/{operation_id}", follow_operation, methods=["GET"], response_model=FollowJob
)


router.add_api_route(
    "/3/feed/{user_id}", get_user_feed, methods=["GET"], response_model=FeedResponse
)


@router.get("/4/recommendations/{user_id}")
async def recommendations(
    user_id: UUID,
    use_case: Annotated[SocialRecommendationsUseCase, Depends(get_recommendations_use_case)],
    demo_mode: DemoModeDep,
) -> tuple[UUID, ...]:
    return await use_case.recommendations(user_id)


@router.get("/4/mutual-friends")
async def mutual_friends(
    query: Annotated[MutualFriendsRequest, Query()],
    use_case: Annotated[SocialRecommendationsUseCase, Depends(get_recommendations_use_case)],
    demo_mode: DemoModeDep,
) -> tuple[UUID, ...]:
    return await use_case.mutual_friends(query.user_id, query.other_user_id)


@router.post("/5/reaction", response_model=OperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def react(
    payload: ReactionCreate,
    use_case: Annotated[InteractWithPostUseCase, Depends(get_interaction_use_case)],
) -> OperationResponse:
    operation = await use_case.react(
        Reaction(post_id=payload.post_id, user_id=payload.user_id, kind=payload.kind)
    )
    return OperationResponse(operation_id=operation.operation_id, status=operation.status.value)


@router.delete("/5/reaction", response_model=OperationResponse)
async def remove_reaction(
    payload: ReactionRemove,
    use_case: Annotated[InteractWithPostUseCase, Depends(get_interaction_use_case)],
) -> OperationResponse:
    operation = await use_case.remove_reaction(payload.post_id, payload.user_id)
    return OperationResponse(operation_id=operation.operation_id, status=operation.status.value)


@router.post("/5/comment", response_model=OperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def comment(
    payload: CommentCreate,
    use_case: Annotated[InteractWithPostUseCase, Depends(get_interaction_use_case)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> OperationResponse:
    operation = await use_case.comment(
        Comment(post_id=payload.post_id, user_id=payload.user_id, text=payload.text),
        idempotency_key,
    )
    return OperationResponse(operation_id=operation.operation_id, status=operation.status.value)


@router.post("/6/message", status_code=status.HTTP_202_ACCEPTED)
async def send_message(
    payload: MessageCreate,
    use_case: Annotated[SendGroupMessageUseCase, Depends(get_message_use_case)],
    demo_mode: DemoModeDep,
) -> None:
    if demo_mode:
        return
    await use_case.execute(
        Message(
            conversation_id=payload.conversation_id,
            sender_id=payload.sender_id,
            text=payload.text,
            read_by=frozenset({payload.sender_id}),
        )
    )


@router.post("/7/moderate", status_code=status.HTTP_204_NO_CONTENT)
async def moderate(
    payload: ModerationRequest,
    use_case: Annotated[ModeratePostUseCase, Depends(get_moderation_use_case)],
    actor: ModeratorDep,
) -> None:
    from fastapi import HTTPException

    if payload.moderator_id != actor.id:
        raise HTTPException(status_code=403, detail="moderator_id must match bearer identity")
    await use_case.moderate_post(payload.report_id, payload.post_id, actor.id, payload.decision)


@router.post("/8/suspend", status_code=status.HTTP_204_NO_CONTENT)
async def suspend(
    payload: SuspensionRequest,
    response: Response,
    use_case: Annotated[SuspendAndTraceUserUseCase, Depends(get_suspend_trace_use_case)],
    actor: ModeratorDep,
) -> None:
    """Compatibility route: queues work; inspect /accounts/{user_id}/history/operations."""
    job = await use_case.suspend_user(payload.user_id, payload.reason, actor.id)
    response.headers["Operation-Id"] = str(job.operation_id)
    response.headers["Location"] = f"/api/v1/accounts/operations/{job.operation_id}"


@router.get("/8/trace/{user_id}", response_model=UserTraceResponse)
async def trace(
    user_id: UUID,
    use_case: Annotated[SuspendAndTraceUserUseCase, Depends(get_suspend_trace_use_case)],
    actor: CurrentUserDep,
) -> object:
    from fastapi import HTTPException

    if actor.id != user_id and actor.role not in ("moderator", "admin"):
        raise HTTPException(status_code=403, detail="Only owner or moderator may trace")
    return await use_case.trace_user(user_id)
