import logging

import asyncpg
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from app import database, redis
from app.config import VERSION

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health(response: Response):
    components = {}

    # Database check
    try:
        conn: asyncpg.Connection = await database._pool.acquire()
        await conn.fetchval("SELECT 1")
        await database._pool.release(conn)
        components["database"] = "ok"
    except Exception as exc:
        logger.warning(f"health: database check failed: {exc}")
        components["database"] = "error"

    # Redis check
    try:
        r = await redis.get_redis()
        await r.ping()
        components["redis"] = "ok"
    except Exception as exc:
        logger.warning(f"health: redis check failed: {exc}")
        components["redis"] = "error"

    # Worker check: look for a recent heartbeat key written by Celery beat
    # In Phase 1 there is no dedicated heartbeat task, so we check if the
    # Celery broker (Redis) is reachable and infer worker status from that.
    components["worker"] = "ok" if components["redis"] == "ok" else "unknown"

    overall = "ok" if all(v == "ok" for v in components.values()) else "degraded"
    status_code = 200 if overall == "ok" else 503

    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "components": components, "version": VERSION},
    )
