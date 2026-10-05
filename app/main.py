from fastapi import FastAPI

from app.api.exception_handlers import install_exception_handlers
from app.api.v1.router import api_router
from app.api.v1.routers.health import router as health_router
from app.core.config import get_settings
from app.core.lifespan import build_lifespan
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.app_debug)
    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=build_lifespan(settings),
    )
    install_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()

