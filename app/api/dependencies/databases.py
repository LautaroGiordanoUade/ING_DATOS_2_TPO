from typing import Annotated, cast

from fastapi import Depends, Request

from app.core.lifespan import Resources


def get_resources(request: Request) -> Resources:
    return cast(Resources, request.app.state.resources)


ResourcesDep = Annotated[Resources, Depends(get_resources)]

