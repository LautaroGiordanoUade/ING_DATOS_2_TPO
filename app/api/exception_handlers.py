from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.application.ports import InjectedFailureError
from app.core.exceptions import (
    ConflictError,
    FeatureNotImplementedError,
    InvalidOperationError,
    ResourceNotFoundError,
)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(FeatureNotImplementedError)
    async def feature_not_implemented(
        request: Request, exc: FeatureNotImplementedError
    ) -> JSONResponse:
        del request
        return JSONResponse(status_code=501, content={"detail": str(exc), "code": "todo_tp"})

    @app.exception_handler(ResourceNotFoundError)
    async def not_found(request: Request, exc: ResourceNotFoundError) -> JSONResponse:
        del request
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict(request: Request, exc: ConflictError) -> JSONResponse:
        del request
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(InvalidOperationError)
    async def invalid_operation(request: Request, exc: InvalidOperationError) -> JSONResponse:
        del request
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(InjectedFailureError)
    async def injected_failure(request: Request, exc: InjectedFailureError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc), "code": "injected_demo_failure"},
        )

