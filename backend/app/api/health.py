import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import get_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    """The process is up. Checks nothing else, so a DB outage doesn't get the container killed."""
    return {"status": "ok"}


@router.get("/ready", response_model=None)
def ready(engine: Annotated[Engine, Depends(get_engine)]) -> dict[str, str] | JSONResponse:
    """The app can serve traffic: Postgres is reachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # The reason goes to the log only; the response stays generic.
        logger.exception("Readiness check failed: database unreachable")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
