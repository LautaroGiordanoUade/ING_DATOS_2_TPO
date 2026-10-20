import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.application.ports import NoOpFailureInjector
from app.application.services import CompensationService, OperationStatus
from app.application.use_cases.problem_05_interact_with_post import InteractWithPostUseCase
from app.domain.entities import Comment, Post, Reaction
from app.infrastructure.persistence.memory import InMemoryOperationLogRepository
from app.infrastructure.persistence.redis.reaction_lock import RedisReactionLock


class LocalReactionLock:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, post_id: UUID) -> AsyncIterator[None]:
        async with self.lock:
            yield


def make_use_case(
    posts: AsyncMock,
    reactions: AsyncMock,
    counters: AsyncMock,
    notifications: AsyncMock,
    log: InMemoryOperationLogRepository,
    lock: LocalReactionLock,
) -> InteractWithPostUseCase:
    return InteractWithPostUseCase(
        posts,
        reactions,
        AsyncMock(),
        counters,
        notifications,
        CompensationService(log, NoOpFailureInjector()),
        reaction_lock=lock,
    )


@pytest.mark.parametrize("action", ["reaction", "comment"])
async def test_notification_partial_failure_is_compensated(action: str) -> None:
    post = Post(user_id=uuid4(), text="test")
    posts, reactions, counters, notifications = (AsyncMock() for _ in range(4))
    posts.get.return_value = post
    reactions.upsert.return_value = None
    pending: dict[str, dict[str, object]] = {}

    async def partial_publish(recipient: UUID, event: dict[str, object]) -> None:
        pending[str(event["event_id"])] = event
        raise ConnectionError("PUBLISH failed after HSET")

    async def revoke(recipient: UUID, event_id: UUID) -> None:
        pending.pop(str(event_id), None)

    notifications.publish.side_effect = partial_publish
    notifications.revoke.side_effect = revoke
    log = InMemoryOperationLogRepository()
    uc = make_use_case(posts, reactions, counters, notifications, log, LocalReactionLock())
    with pytest.raises(ConnectionError):
        if action == "reaction":
            await uc.react(Reaction(post_id=post.id, user_id=uuid4(), kind="like"))
        else:
            await uc.comment(Comment(post_id=post.id, user_id=uuid4(), text="test"))
    assert pending == {}
    assert counters.increment.await_args_list[-1].args[-1] == -1
    assert all(op.status == OperationStatus.COMPENSATED for op in log._operations.values())


async def test_delete_waits_for_creation_before_updating_counter() -> None:
    post = Post(user_id=uuid4(), text="test")
    actor = uuid4()
    posts, reactions, counters, notifications = (AsyncMock() for _ in range(4))
    posts.get.return_value = post
    written, resume = asyncio.Event(), asyncio.Event()
    state: dict[str, Any] = {"reaction": None, "counter": 0}

    async def upsert(reaction: Reaction) -> None:
        state["reaction"] = reaction
        written.set()
        await resume.wait()
        return None

    async def delete(*args: UUID) -> Reaction | None:
        previous = state["reaction"]
        state["reaction"] = None
        return previous if isinstance(previous, Reaction) else None

    async def increment(namespace: str, post_id: UUID, amount: int) -> int:
        state["counter"] = max(0, state["counter"] + amount)
        return int(state["counter"])

    reactions.upsert.side_effect = upsert
    reactions.delete_for_user.side_effect = delete
    counters.increment.side_effect = increment
    log, lock = InMemoryOperationLogRepository(), LocalReactionLock()
    creator = make_use_case(posts, reactions, counters, notifications, log, lock)
    remover = make_use_case(posts, reactions, counters, notifications, log, lock)
    creation = asyncio.create_task(
        creator.react(Reaction(post_id=post.id, user_id=actor, kind="like"))
    )
    await asyncio.wait_for(written.wait(), 2)
    deletion = asyncio.create_task(remover.remove_reaction(post.id, actor))
    await asyncio.sleep(0)
    reactions.delete_for_user.assert_not_awaited()
    resume.set()
    await asyncio.wait_for(asyncio.gather(creation, deletion), 2)
    assert state == {"reaction": None, "counter": 0}


async def test_redis_lock_releases_after_exception() -> None:
    client = AsyncMock()
    from unittest.mock import Mock

    acquired = AsyncMock()
    acquired.acquire.return_value = True
    client.lock = Mock(return_value=acquired)
    with pytest.raises(ValueError):
        async with RedisReactionLock(client).hold(uuid4()):
            raise ValueError("failure")
    acquired.release.assert_awaited_once()
