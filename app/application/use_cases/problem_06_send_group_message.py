import logging
from uuid import UUID

from app.application.ports.failure_injector import FailureInjector, NoOpFailureInjector
from app.application.ports.messaging import (
    Group,
    GroupCreate,
    GroupMessage,
    MessagePage,
    MessagingLock,
    MessagingStore,
    MessagingViews,
    Participant,
)
from app.core.exceptions import ConflictError, InvalidOperationError, ResourceNotFoundError

logger = logging.getLogger(__name__)


class SendGroupMessageUseCase:
    """Mongo-first messaging; forward recovery, never revoke persisted history."""

    def __init__(self, store: MessagingStore, views: MessagingViews, lock: MessagingLock) -> None:
        self.store = store
        self.views = views
        self.lock = lock

    @staticmethod
    def key(key: str) -> str:
        if not key.strip() or len(key) > 128:
            raise InvalidOperationError("Idempotency-Key debe tener entre 1 y 128 caracteres")
        return key

    async def active(self, actor: UUID) -> None:
        if not await self.store.participants([actor]):
            raise ResourceNotFoundError("Usuario no disponible")

    async def member(self, group_id: UUID, actor: UUID) -> Group:
        await self.active(actor)
        group = await self.store.group(group_id)
        if group is None or actor not in group.participant_ids:
            raise ResourceNotFoundError("Conversación no disponible")
        return group

    async def search(self, actor: UUID, query: str) -> list[Participant]:
        await self.active(actor)
        return await self.store.search(actor, query.strip())

    async def create(self, actor: UUID, payload: GroupCreate, key: str) -> Group:
        self.key(key)
        ids = list({actor, *payload.participant_ids})
        if len(ids) < 2 or len(ids) > 20:
            raise InvalidOperationError("El grupo debe tener entre 2 y 20 participantes")
        if len(await self.store.participants(ids)) != len(ids):
            raise InvalidOperationError("Todos los participantes deben estar activos")
        return await self.store.create_group(actor, payload, key)

    async def groups(self, actor: UUID, before: UUID | None, limit: int) -> list[Group]:
        await self.active(actor)
        groups = await self.store.groups(actor, before, limit)
        for group in groups:
            async with self.lock.hold(group.id):
                await self._sync(group.id)
                group.unread = await self.views.unread(group.id, actor)
                group.participants = await self.store.participants(group.participant_ids)
        return groups

    async def send(
        self,
        group_id: UUID,
        actor: UUID,
        text: str,
        key: str,
        injector: FailureInjector | None = None,
    ) -> GroupMessage:
        self.key(key)
        if not text.strip() or len(text.strip()) > 4000:
            raise InvalidOperationError("El mensaje debe tener entre 1 y 4000 caracteres")
        async with self.lock.hold(group_id):
            group = await self.member(group_id, actor)
            await (injector or NoOpFailureInjector()).checkpoint("p6_before_persist")
            message = await self.store.send(group, actor, text.strip(), key)
            if message.delivery_status == "completed":
                return message
            try:
                await (injector or NoOpFailureInjector()).checkpoint("p6_after_persist")
                await self._sync(group_id, injector)
            except Exception as exc:
                logger.warning("P6 message %s awaits forward recovery: %s", message.id, exc)
                await self.store.failed(message.id, str(exc))
            return await self._required_message(message.id)

    async def _required_message(self, message_id: UUID) -> GroupMessage:
        message = await self.store.message(message_id)
        if message is None:
            raise ResourceNotFoundError("Mensaje no disponible")
        return message

    async def status(self, message_id: UUID, actor: UUID) -> GroupMessage:
        message = await self._required_message(message_id)
        await self.member(message.conversation_id, actor)
        return message

    async def history(
        self,
        group_id: UUID,
        actor: UUID,
        before: int | None,
        limit: int,
    ) -> MessagePage:
        await self.member(group_id, actor)
        return await self.store.history(group_id, before, limit)

    async def read(self, group_id: UUID, actor: UUID, message_id: UUID) -> int:
        async with self.lock.hold(group_id):
            await self.member(group_id, actor)
            message = await self._required_message(message_id)
            if message.conversation_id != group_id:
                raise InvalidOperationError("El mensaje no pertenece a esta conversación")
            await self.store.read(group_id, actor, message.sequence)
            try:
                await self._sync(group_id)
            except Exception:
                logger.exception("P6 read saved; Redis synchronization pending")
            group = await self.member(group_id, actor)
            return await self.store.unread(group, actor)

    async def _sync(self, group_id: UUID, injector: FailureInjector | None = None) -> None:
        group = await self.store.group(group_id)
        if group is None:
            return
        for actor in group.participant_ids:
            await self.views.set_unread(group_id, actor, await self.store.unread(group, actor))
        await (injector or NoOpFailureInjector()).checkpoint("p6_after_unread")
        active = {p.id for p in await self.store.participants(group.participant_ids)}
        for message in await self.store.pending_messages(group_id):
            await self.store.checkpoint(message.id, "redis_unread")
            for recipient in group.participant_ids:
                if recipient != message.sender_id and recipient in active:
                    await self.views.notify(message, recipient)
                    await self.store.checkpoint(message.id, f"redis_notify:{recipient}")
                    await (injector or NoOpFailureInjector()).checkpoint("p6_after_notify")
            await self.store.complete(message.id)
        await self.store.dirty(group_id, False)

    async def recover_pending(self) -> None:
        for group_id in await self.store.pending_groups():
            try:
                async with self.lock.hold(group_id):
                    await self._sync(group_id)
            except ConflictError:
                continue
            except Exception:
                logger.exception("P6 conversation %s still pending", group_id)
