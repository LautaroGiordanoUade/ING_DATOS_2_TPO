import asyncio
from collections.abc import Awaitable

from fastapi import APIRouter, Response, status

from app.api.dependencies.databases import ResourcesDep
from app.core.config import get_settings
from app.schemas.models import HealthResponse, ReadinessResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


async def _status(check: Awaitable[object]) -> str:
    try:
        await asyncio.wait_for(check, timeout=2.0)
    except Exception:
        return "unavailable"
    return "ok"


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(resources: ResourcesDep, response: Response) -> ReadinessResponse:
    mongo_database = resources.mongo_client[get_settings().mongodb_database]
    checks = await asyncio.gather(
        _status(mongo_database.command("ping")),
        _status(resources.redis.ping()),
        _status(resources.neo4j.verify_connectivity()),
    )
    services = dict(zip(("mongodb", "redis", "neo4j"), checks, strict=True))
    overall = "ready" if all(value == "ok" for value in services.values()) else "degraded"
    if overall != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status=overall, services=services)

