import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import UUID

from neo4j.exceptions import ServiceUnavailable, SessionExpired, TransientError
from pymongo.errors import ConnectionFailure, ExecutionTimeout
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

logger = logging.getLogger(__name__)
_TRANSIENT = (
    ConnectionFailure,
    ExecutionTimeout,
    RedisConnectionError,
    RedisTimeoutError,
    ConnectionError,
    TimeoutError,
    ServiceUnavailable,
    SessionExpired,
    TransientError,
)


class WorkflowJob(Protocol):
    operation_id: UUID
    completed_steps: list[str]
    failures: list[str]
    fail_at: str | None


class WorkflowStore[T](Protocol):
    async def save(self, job: T) -> None: ...


class WorkflowSteps[T: WorkflowJob]:
    def __init__(self, store: WorkflowStore[T]) -> None:
        self._workflow_store = store

    async def _retry[R](self, job: T, name: str, action: Callable[[], Awaitable[R]]) -> R:
        for attempt in range(3):
            try:
                return await action()
            except _TRANSIENT as exc:
                message = f"{name} attempt {attempt + 1}: {exc}"
                logger.warning("Workflow %s %s", job.operation_id, message)
                job.failures.append(message)
                await self._workflow_store.save(job)
                if attempt == 2:
                    raise
                await asyncio.sleep(0.05 * 2**attempt)
        raise AssertionError("Retry loop exhausted")

    async def _step(self, job: T, name: str, action: Callable[[], Awaitable[None]]) -> None:
        if name in job.completed_steps:
            return
        await self._retry(job, name, action)
        if job.fail_at == name:
            raise RuntimeError(f"Injected failure after {name}")
        job.completed_steps.append(name)
        await self._workflow_store.save(job)
