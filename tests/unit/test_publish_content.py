import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.application.services.operation import OperationContext, OperationStatus
from app.application.services.publication_job import PublicationJob
from app.application.services.publication_processor import PublicationProcessor
from app.application.use_cases.problem_01_publish_content import PublishContentUseCase
from app.core.exceptions import InvalidOperationError
from app.domain.entities import Post


class JobStore:
    def __init__(self) -> None:
        self.saved: PublicationJob | None = None
        self.post_exists = False
        self.active = False

    async def save(self, job: PublicationJob) -> None:
        self.saved = deepcopy(job)

    async def stage_post(self, job: PublicationJob) -> None:
        self.post_exists = True

    async def activate_post(self, job: PublicationJob) -> None:
        self.active = True

    async def delete_post(self, job: PublicationJob) -> None:
        self.post_exists = False

    async def enqueue(self, post: Post, key: str | None, fail_at: str | None) -> PublicationJob:
        raise NotImplementedError

    async def pending(self) -> tuple[PublicationJob, ...]:
        return ()


class FeedStore:
    def __init__(self) -> None:
        self.members: set[UUID] = set()
        self.visible = False
        self.crash = False
        self.fail_commit = False
        self.fail_rollback = False

    async def stage_batch(self, users: tuple[UUID, ...], post_id: UUID, score: float) -> None:
        self.members.update(users)
        if self.crash:
            self.crash = False
            raise asyncio.CancelledError

    async def commit(self, post_id: UUID) -> None:
        self.visible = True
        if self.fail_commit:
            self.fail_commit = False
            raise ConnectionError("Lost commit acknowledgement")

    async def abort(self, post_id: UUID) -> None:
        self.visible = False

    async def remove_batch(self, users: tuple[UUID, ...], post_id: UUID) -> None:
        if self.fail_rollback:
            self.fail_rollback = False
            raise ConnectionError("Redis unavailable during rollback")
        self.members.difference_update(users)


def new_job(fail_at: str | None = None) -> PublicationJob:
    return PublicationJob(
        Post(user_id=uuid4(), text="test", interests=("datos",)),
        OperationContext("problem_01_publish_content"),
        "fingerprint",
        fail_at=fail_at,
    )


async def test_publication_distributes_in_batches_then_becomes_visible() -> None:
    jobs, feeds, graph = JobStore(), FeedStore(), AsyncMock()
    followers = tuple(uuid4() for _ in range(501))
    graph.follower_ids.return_value = followers
    job = new_job()
    await PublicationProcessor(jobs, graph, feeds).process(job)
    assert feeds.members == set(followers)
    assert feeds.visible and jobs.active and jobs.post_exists
    assert job.offset == 501
    assert job.operation.status == OperationStatus.COMPLETED


@pytest.mark.parametrize(
    "step",
    [
        "mongo_create_post",
        "neo4j_load_followers",
        "redis_feed_update",
        "redis_feed_partial",
        "publication_commit",
    ],
)
async def test_injected_failure_removes_every_partial_effect(step: str) -> None:
    jobs, feeds, graph = JobStore(), FeedStore(), AsyncMock()
    graph.follower_ids.return_value = tuple(uuid4() for _ in range(501))
    job = new_job(step)
    await PublicationProcessor(jobs, graph, feeds).process(job)
    assert job.operation.status == OperationStatus.COMPENSATED
    assert not feeds.members and not feeds.visible and not jobs.post_exists


async def test_restart_replays_batch_after_lost_cursor_without_duplicates() -> None:
    jobs, feeds, graph = JobStore(), FeedStore(), AsyncMock()
    followers = tuple(uuid4() for _ in range(501))
    graph.follower_ids.return_value = followers
    feeds.crash = True
    with pytest.raises(asyncio.CancelledError):
        await PublicationProcessor(jobs, graph, feeds).process(new_job())
    assert jobs.saved is not None and jobs.saved.offset == 0
    assert feeds.members and not feeds.visible
    await PublicationProcessor(jobs, graph, feeds).process(deepcopy(jobs.saved))
    assert feeds.members == set(followers) and feeds.visible
    graph.follower_ids.assert_awaited_once()


async def test_failed_compensation_is_retried_after_restart() -> None:
    jobs, feeds, graph = JobStore(), FeedStore(), AsyncMock()
    graph.follower_ids.return_value = (uuid4(), uuid4())
    feeds.fail_rollback = True
    with pytest.raises(ConnectionError):
        await PublicationProcessor(jobs, graph, feeds).process(new_job("redis_feed_partial"))
    assert jobs.saved is not None and jobs.saved.rollback
    await PublicationProcessor(jobs, graph, feeds).process(deepcopy(jobs.saved))
    assert not feeds.members and not jobs.post_exists
    assert jobs.saved.operation.status == OperationStatus.COMPENSATED


async def test_lost_commit_response_is_completed_instead_of_rolled_back() -> None:
    jobs, feeds, graph = JobStore(), FeedStore(), AsyncMock()
    graph.follower_ids.return_value = (uuid4(),)
    feeds.fail_commit = True
    with pytest.raises(ConnectionError):
        await PublicationProcessor(jobs, graph, feeds).process(new_job())
    assert jobs.saved is not None and "publication_commit" in jobs.saved.operation.completed_steps
    assert feeds.visible
    await PublicationProcessor(jobs, graph, feeds).process(deepcopy(jobs.saved))
    assert feeds.visible and jobs.post_exists
    assert jobs.saved.operation.status == OperationStatus.COMPLETED


async def test_no_followers_is_a_valid_publication() -> None:
    jobs, feeds, graph = JobStore(), FeedStore(), AsyncMock()
    graph.follower_ids.return_value = ()
    job = new_job()
    await PublicationProcessor(jobs, graph, feeds).process(job)
    assert job.operation.status == OperationStatus.COMPLETED and feeds.visible


async def test_publish_requires_interests_without_enqueuing_invalid_payload() -> None:
    jobs = AsyncMock()
    with pytest.raises(InvalidOperationError):
        await PublishContentUseCase(jobs).execute(Post(user_id=uuid4(), text="missing interests"))
    jobs.enqueue.assert_not_awaited()
