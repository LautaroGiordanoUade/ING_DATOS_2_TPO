from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.application.ports import InjectedFailureError
from app.application.services.workflow import _TRANSIENT
from app.core.exceptions import (
    AuthenticationError,
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

    @app.exception_handler(AuthenticationError)
    async def authentication_failed(request: Request, exc: AuthenticationError) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=401, content={"detail": str(exc)}, headers={"WWW-Authenticate": "Bearer"}
        )

    async def storage_unavailable(request: Request, exc: Exception) -> JSONResponse:
        del request, exc
        return JSONResponse(
            status_code=503, content={"detail": "Required storage temporarily unavailable"}
        )

    for error_type in _TRANSIENT:
        app.add_exception_handler(error_type, storage_unavailable)
