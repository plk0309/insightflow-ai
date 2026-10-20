from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings
from app.api.auth import router as auth_router


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "InsightFlow AI — Autonomous Business Intelligence "
            "and Analytics Platform"
        ),
        debug=settings.DEBUG,
    )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1/auth")

    @app.get("/", tags=["Root"])
    def root():
        return {
            "message": "Welcome to InsightFlow AI",
            "version": settings.APP_VERSION,
            "docs": "/docs",
        }

    return app


app = create_app()