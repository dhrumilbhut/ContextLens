import json
from typing import Optional

import asyncpg


async def update_trace_status(
    conn: asyncpg.Connection,
    trace_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    if error_message is not None:
        await conn.execute(
            """
            UPDATE traces
            SET status = $1, error_message = $2, failed_at = NOW()
            WHERE id = $3::uuid
            """,
            status,
            error_message,
            trace_id,
        )
    else:
        await conn.execute(
            "UPDATE traces SET status = $1 WHERE id = $2::uuid",
            status,
            trace_id,
        )


async def create_trace(
    conn: asyncpg.Connection,
    query: str,
    chunks: list[dict],
    llm_response: str,
    latency_ms: Optional[int],
    project_id: str,
) -> str:
    trace_id = await conn.fetchval(
        """
        INSERT INTO traces (project_id, query_text, retrieved_chunks, llm_response, latency_ms, status)
        VALUES ($1::uuid, $2, $3::jsonb, $4, $5, 'pending')
        RETURNING id::text
        """,
        project_id,
        query,
        json.dumps(chunks),
        llm_response,
        latency_ms,
    )
    return trace_id


async def get_today_processed(conn: asyncpg.Connection, project_id: str) -> int:
    row = await conn.fetchrow(
        """
        SELECT traces_processed FROM usage_records
        WHERE project_id = $1::uuid AND date = CURRENT_DATE
        """,
        project_id,
    )
    return row["traces_processed"] if row else 0


async def increment_usage(
    conn: asyncpg.Connection,
    project_id: str,
    ingested: bool = False,
    processed: bool = False,
) -> None:
    await conn.execute(
        """
        INSERT INTO usage_records (project_id, date, traces_ingested, traces_processed)
        VALUES ($1::uuid, CURRENT_DATE, $2, $3)
        ON CONFLICT (project_id, date) DO UPDATE SET
            traces_ingested = usage_records.traces_ingested + EXCLUDED.traces_ingested,
            traces_processed = usage_records.traces_processed + EXCLUDED.traces_processed,
            updated_at = NOW()
        """,
        project_id,
        int(ingested),
        int(processed),
    )
