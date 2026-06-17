import logging

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.database import get_db
from app.middleware.auth import get_project_from_api_key
from app.middleware.rate_limit import RateLimitError, check_rate_limits
from app.models.traces import IngestRequest, IngestResponse
from app.redis import get_redis
from app.services.trace_service import (
    create_trace,
    get_today_processed,
    increment_usage,
)
from app.worker.tasks import process_trace

router = APIRouter()
logger = logging.getLogger(__name__)


async def _is_processing_blocked(conn: asyncpg.Connection, project_id: str) -> bool:
    if settings.DAILY_PROCESSING_LIMIT <= 0:
        return False
    today_processed = await get_today_processed(conn, project_id)
    return today_processed >= settings.DAILY_PROCESSING_LIMIT


@router.post("/ingest", status_code=202, response_model=IngestResponse)
async def ingest(
    request: IngestRequest,
    conn: asyncpg.Connection = Depends(get_db),
    project_id: str = Depends(get_project_from_api_key),
    redis: aioredis.Redis = Depends(get_redis),
):
    # Step 1: Rate limiting (Redis — fast, in memory)
    try:
        await check_rate_limits(redis, project_id)
    except RateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    # Step 2: Check daily processing limit (Postgres)
    processing_blocked = await _is_processing_blocked(conn, project_id)

    # Step 3: Store trace (always — ingestion is never blocked)
    chunks_data = [c.model_dump() for c in request.chunks]
    trace_id = await create_trace(
        conn=conn,
        query=request.query,
        chunks=chunks_data,
        llm_response=request.response,
        latency_ms=request.latency_ms,
        project_id=project_id,
    )

    # Step 4: Increment traces_ingested (always)
    await increment_usage(conn, project_id, ingested=True)

    # Step 5: Enqueue for processing only if limit not reached
    if not processing_blocked:
        process_trace.delay(trace_id)
    else:
        logger.warning(
            f"daily processing limit reached for project {project_id} — "
            f"trace {trace_id} stored but not enqueued"
        )

    return IngestResponse(trace_id=trace_id, status="pending")
