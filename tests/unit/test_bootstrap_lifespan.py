from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI

import app.core.lifespan as lifecycle
from app.core.config import Settings


@pytest.mark.parametrize("fails", [False, True])
async def test_bootstrap_precedes_requests_and_closes_resources(
    monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
    mongo, redis, neo4j = MagicMock(), MagicMock(), MagicMock()
    mongo.close, redis.aclose, neo4j.close = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(lifecycle, "create_mongo_client", lambda url: mongo)
    monkeypatch.setattr(lifecycle, "create_redis_client", lambda url: redis)
    monkeypatch.setattr(lifecycle, "create_neo4j_driver", lambda *args: neo4j)
    initializer = AsyncMock(return_value={"indexes_verified": True})
    if fails:
        initializer.side_effect = RuntimeError("required indexes unavailable")
    monkeypatch.setattr(lifecycle, "initialize_database", initializer)
    settings = Settings(app_env="development")
    app = FastAPI()
    context = lifecycle.build_lifespan(settings)(app)
    if fails:
        with pytest.raises(RuntimeError, match="required indexes"):
            async with context:
                pytest.fail("API must not serve before database initialization succeeds")
    else:
        async with context:
            initializer.assert_awaited_once_with(mongo[settings.mongodb_database], development=True)
            mongo.close.assert_not_awaited()
    mongo.close.assert_awaited_once()
    redis.aclose.assert_awaited_once()
    neo4j.close.assert_awaited_once()
