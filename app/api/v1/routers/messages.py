from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

from app.api.dependencies.auth import CurrentUserDep
from app.api.dependencies.use_cases import FailureInjectorDep, get_message_use_case
from app.application.ports.messaging import (
    Group,
    GroupCreate,
    GroupMessage,
    MessagePage,
    MessageText,
    Participant,
    ReadThrough,
)
from app.application.use_cases.problem_06_send_group_message import SendGroupMessageUseCase

router = APIRouter()
MessagingDep = Annotated[SendGroupMessageUseCase, Depends(get_message_use_case)]
RequestKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


@router.get("/participants", response_model=list[Participant])
async def participants(
    actor: CurrentUserDep,
    service: MessagingDep,
    q: Annotated[str, Query(min_length=2, max_length=50)],
) -> list[Participant]:
    return await service.search(actor.id, q)


@router.post("/conversations", response_model=Group, status_code=201)
async def create_conversation(
    payload: GroupCreate,
    actor: CurrentUserDep,
    service: MessagingDep,
    key: RequestKey,
) -> Group:
    return await service.create(actor.id, payload, key)


@router.get("/conversations", response_model=list[Group])
async def conversations(
    actor: CurrentUserDep,
    service: MessagingDep,
    before: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[Group]:
    return await service.groups(actor.id, before, limit)


@router.get("/conversations/{conversation_id}", response_model=Group)
async def conversation(
    conversation_id: UUID, actor: CurrentUserDep, service: MessagingDep
) -> Group:
    group = await service.member(conversation_id, actor.id)
    group.participants = await service.store.participants(group.participant_ids)
    group.unread = await service.store.unread(group, actor.id)
    return group


@router.get("/conversations/{conversation_id}/messages", response_model=MessagePage)
async def history(
    conversation_id: UUID,
    actor: CurrentUserDep,
    service: MessagingDep,
    before: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 30,
) -> MessagePage:
    return await service.history(conversation_id, actor.id, before, limit)


@router.post(
    "/conversations/{conversation_id}/messages", response_model=GroupMessage, status_code=202
)
async def create_message(
    conversation_id: UUID,
    payload: MessageText,
    actor: CurrentUserDep,
    service: MessagingDep,
    key: RequestKey,
    injector: FailureInjectorDep,
) -> GroupMessage:
    return await service.send(conversation_id, actor.id, payload.text, key, injector)


@router.put("/conversations/{conversation_id}/read")
async def mark_read(
    conversation_id: UUID,
    payload: ReadThrough,
    actor: CurrentUserDep,
    service: MessagingDep,
) -> dict[str, int]:
    """Advance monotonically through a real message; replay never decrements twice."""
    return {"unread": await service.read(conversation_id, actor.id, payload.message_id)}


@router.get("/{message_id}/delivery", response_model=GroupMessage)
async def delivery(message_id: UUID, actor: CurrentUserDep, service: MessagingDep) -> GroupMessage:
    return await service.status(message_id, actor.id)
