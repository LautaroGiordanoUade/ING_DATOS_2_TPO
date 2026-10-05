from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.lifespan import Resources


def get_resources(request: Request) -> Resources:
    return cast(Resources, request.app.state.resources)


ResourcesDep = Annotated[Resources, Depends(get_resources)]


async def get_postgres_session(resources: ResourcesDep) -> AsyncIterator[AsyncSession]:
    async with resources.postgres_sessions() as session:
        yield session


PostgresSessionDep = Annotated[AsyncSession, Depends(get_postgres_session)]

