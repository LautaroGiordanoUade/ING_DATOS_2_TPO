from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status

from app.api.demo_data import (
    DEMO_OPERATION_ID,
    DEMO_OTHER_USER_ID,
    DEMO_USER_ID,
    demo_feed,
    demo_trace,
)
from app.api.dependencies.databases import ResourcesDep
from app.api.dependencies.demo import DemoModeDep
from app.api.dependencies.use_cases import (
    get_feed_use_case,
    get_follow_use_case,
    get_interaction_use_case,
    get_message_use_case,
    get_moderation_use_case,
    get_publish_use_case,
    get_recommendations_use_case,
    get_suspend_trace_use_case,
)
from app.application.services import OperationContext, OperationStatus
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
from app.core.exceptions import ResourceNotFoundError
from app.domain.entities import Comment, Message, Post, Reaction
from app.schemas.models import (
    CommentCreate,
    FeedResponse,
    FollowRequest,
    MessageCreate,
    ModerationRequest,
    MutualFriendsRequest,
    OperationDetailResponse,
    OperationResponse,
    PostCreate,
    ReactionCreate,
    ReactionRemove,
    SuspensionRequest,
    UserTraceResponse,
)

router = APIRouter()


@router.get("/operations/{operation_id}", response_model=OperationDetailResponse)
async def get_operation(operation_id: UUID, resources: ResourcesDep) -> OperationDetailResponse:
    operation = await resources.operation_log.get(operation_id)
    if operation is None:
        raise ResourceNotFoundError("Operación no encontrada")
    return OperationDetailResponse(
        operation_id=operation.operation_id,
        operation_type=operation.operation_type,
        status=operation.status.value,
        current_step=operation.current_step,
        completed_steps=operation.completed_steps,
        error=operation.error,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
    )

@router.post("/1/publish", response_model=OperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def publish(
    payload: PostCreate,
    use_case: Annotated[PublishContentUseCase, Depends(get_publish_use_case)],
    resources: ResourcesDep,
    demo_mode: DemoModeDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> OperationResponse:
    # TODO(TP): Integrar la clave con IdempotencyService y persistir resultado.
    del idempotency_key
    if demo_mode:
        operation = OperationContext(
            operation_type="problem_01_publish_content_demo",
            operation_id=DEMO_OPERATION_ID,
            completed_steps=["mock_demo_step"],
            status=OperationStatus.COMPLETED,
        )
        await resources.operation_log.save(operation)
        return OperationResponse(
            operation_id=operation.operation_id,
            status=operation.status.value,
        )
    post = Post(
        user_id=payload.user_id,
        text=payload.text,
        media=tuple(payload.media),
        interests=tuple(payload.interests),
        visibility=payload.visibility,
    )
    operation = await use_case.execute(post)
    return OperationResponse(operation_id=operation.operation_id, status=operation.status.value)

@router.post("/2/follow", status_code=status.HTTP_204_NO_CONTENT)
async def follow(
    payload: FollowRequest,
    use_case: Annotated[FollowUserUseCase, Depends(get_follow_use_case)],
    demo_mode: DemoModeDep,
) -> None:
    if demo_mode:
        return
    await use_case.follow(payload.user_id, payload.followed_user_id)

@router.delete("/2/follow", status_code=status.HTTP_204_NO_CONTENT)
async def unfollow(
    payload: FollowRequest,
    use_case: Annotated[FollowUserUseCase, Depends(get_follow_use_case)],
    demo_mode: DemoModeDep,
) -> None:
    if demo_mode:
        return
    await use_case.unfollow(payload.user_id, payload.followed_user_id)

@router.get("/3/feed/{user_id}", response_model=FeedResponse)
async def feed(
    user_id: UUID,
    use_case: Annotated[GetFeedUseCase, Depends(get_feed_use_case)],
    demo_mode: DemoModeDep,
    cursor: Annotated[str | None, Query()] = None,
) -> object:
    # TODO(TP): Decodificar/validar cursor opaco score+timestamp+UUID.
    del cursor
    if demo_mode:
        return demo_feed(user_id)
    return await use_case.execute(user_id)

@router.get("/4/recommendations/{user_id}")
async def recommendations(
    user_id: UUID,
    use_case: Annotated[SocialRecommendationsUseCase, Depends(get_recommendations_use_case)],
    demo_mode: DemoModeDep,
) -> tuple[UUID, ...]:
    if demo_mode:
        return (DEMO_OTHER_USER_ID,)
    return await use_case.recommendations(user_id)

@router.get("/4/mutual-friends")
async def mutual_friends(
    query: Annotated[MutualFriendsRequest, Query()],
    use_case: Annotated[SocialRecommendationsUseCase, Depends(get_recommendations_use_case)],
    demo_mode: DemoModeDep,
) -> tuple[UUID, ...]:
    if demo_mode:
        return (DEMO_USER_ID,)
    return await use_case.mutual_friends(query.user_id, query.other_user_id)

@router.post("/5/reaction", response_model=OperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def react(
    payload: ReactionCreate,
    use_case: Annotated[InteractWithPostUseCase, Depends(get_interaction_use_case)],
    demo_mode: DemoModeDep,
) -> OperationResponse:
    if demo_mode:
        return OperationResponse(
            operation_id=DEMO_OPERATION_ID, status=OperationStatus.COMPLETED.value
        )
    operation = await use_case.react(
        Reaction(post_id=payload.post_id, user_id=payload.user_id, kind=payload.kind)
    )
    return OperationResponse(operation_id=operation.operation_id, status=operation.status.value)

@router.delete("/5/reaction", response_model=OperationResponse)
async def remove_reaction(
    payload: ReactionRemove,
    use_case: Annotated[InteractWithPostUseCase, Depends(get_interaction_use_case)],
    demo_mode: DemoModeDep,
) -> OperationResponse:
    if demo_mode:
        return OperationResponse(
            operation_id=DEMO_OPERATION_ID, status=OperationStatus.COMPLETED.value
        )
    operation = await use_case.remove_reaction(payload.post_id, payload.user_id)
    return OperationResponse(operation_id=operation.operation_id, status=operation.status.value)

@router.post("/5/comment", response_model=OperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def comment(
    payload: CommentCreate,
    use_case: Annotated[InteractWithPostUseCase, Depends(get_interaction_use_case)],
    demo_mode: DemoModeDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> OperationResponse:
    if demo_mode:
        return OperationResponse(
            operation_id=DEMO_OPERATION_ID, status=OperationStatus.COMPLETED.value
        )
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
    demo_mode: DemoModeDep,
) -> None:
    if demo_mode:
        return
    await use_case.moderate_post(
        payload.report_id, payload.post_id, payload.moderator_id, payload.decision
    )

@router.post("/8/suspend", status_code=status.HTTP_204_NO_CONTENT)
async def suspend(
    payload: SuspensionRequest,
    use_case: Annotated[SuspendAndTraceUserUseCase, Depends(get_suspend_trace_use_case)],
    demo_mode: DemoModeDep,
) -> None:
    if demo_mode:
        return
    await use_case.suspend_user(payload.user_id, payload.reason)

@router.get("/8/trace/{user_id}", response_model=UserTraceResponse)
async def trace(
    user_id: UUID,
    use_case: Annotated[SuspendAndTraceUserUseCase, Depends(get_suspend_trace_use_case)],
    demo_mode: DemoModeDep,
) -> object:
    if demo_mode:
        return demo_trace(user_id)
    return await use_case.trace_user(user_id)

