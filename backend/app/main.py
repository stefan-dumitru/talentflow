import logging

from fastapi import FastAPI

from app.api import health, me, staff
from app.core.config import get_settings
from app.core.errors import RequestIdMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(title="TalentFlow API")
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(staff.router)
    return app


# Module-level instance for `fastapi dev app/main.py` and production servers.
app = create_app()
