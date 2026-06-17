from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.database import get_db
from app.models.projects import (
    ClustersResponse,
    DocumentProblemItem,
    DocumentsProblemsResponse,
    QueryClusterItem,
    UsageDayItem,
    UsageResponse,
    UsageTodayItem,
)
from app.models.traces import (
    AttributionDetail,
    ClaimDetail,
    TraceDetailResponse,
    TraceListItem,
    TraceListResponse,
)
from app.services.project_service import project_exists

router = APIRouter()


@router.get("/projects/{project_id}/traces", response_model=TraceListResponse)
async def list_traces(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    min_faithfulness: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    conn: asyncpg.Connection = Depends(get_db),
):
    if not await project_exists(conn, project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    params: list = [project_id]
    idx = 2
    where_clauses = ["t.project_id = $1::uuid"]

    if status:
        where_clauses.append(f"t.status = ${idx}")
        params.append(status)
        idx += 1

    where_sql = "WHERE " + " AND ".join(where_clauses)
    where_params = list(params)

    having_clause = ""
    if min_faithfulness is not None:
        having_clause = f"HAVING AVG(c.faithfulness_score) >= ${idx}"
        params.append(min_faithfulness)
        idx += 1

    total_row = await conn.fetchrow(
        f"SELECT COUNT(DISTINCT t.id) AS total FROM traces t {where_sql}",
        *where_params,
    )
    total = total_row["total"]

    rows = await conn.fetch(
        f"""
        SELECT
            t.id::text,
            t.query_text,
            t.status,
            t.created_at,
            COUNT(c.id) AS claim_count,
            COUNT(c.id) FILTER (WHERE c.is_faithful = TRUE) AS faithful_claim_count,
            AVG(c.faithfulness_score) AS avg_faithfulness
        FROM traces t
        LEFT JOIN claims c ON c.trace_id = t.id
        {where_sql}
        GROUP BY t.id
        {having_clause}
        ORDER BY t.created_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
        """,
        *params,
        limit,
        offset,
    )

    traces = [
        TraceListItem(
            id=row["id"],
            query_text=row["query_text"],
            status=row["status"],
            claim_count=row["claim_count"] or 0,
            faithful_claim_count=row["faithful_claim_count"] or 0,
            avg_faithfulness=(
                float(row["avg_faithfulness"]) if row["avg_faithfulness"] is not None else None
            ),
            created_at=row["created_at"],
        )
        for row in rows
    ]
    return TraceListResponse(traces=traces, total=total)


@router.get(
    "/projects/{project_id}/traces/{trace_id}",
    response_model=TraceDetailResponse,
)
async def get_trace(
    project_id: str,
    trace_id: str,
    conn: asyncpg.Connection = Depends(get_db),
):
    if not await project_exists(conn, project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    trace_row = await conn.fetchrow(
        """
        SELECT id::text, query_text, llm_response, status, latency_ms, created_at
        FROM traces
        WHERE id = $1::uuid AND project_id = $2::uuid
        """,
        trace_id,
        project_id,
    )
    if not trace_row:
        raise HTTPException(status_code=404, detail="Trace not found")

    claim_rows = await conn.fetch(
        """
        SELECT
            c.id::text,
            c.claim_text,
            c.claim_index,
            c.attributed_chunk_id::text,
            c.attribution_score,
            c.faithfulness_verdict,
            c.faithfulness_score,
            c.is_faithful,
            c.judge_reasoning,
            ch.content AS chunk_content,
            ch.source_document,
            ch.chunk_index AS chunk_index
        FROM claims c
        LEFT JOIN chunks ch ON ch.id = c.attributed_chunk_id
        WHERE c.trace_id = $1::uuid
        ORDER BY c.claim_index ASC
        """,
        trace_id,
    )

    claims = []
    for row in claim_rows:
        attribution = None
        if row["attributed_chunk_id"] is not None:
            attribution = AttributionDetail(
                chunk_id=row["attributed_chunk_id"],
                chunk_content=row["chunk_content"],
                source_document=row["source_document"],
                chunk_index=row["chunk_index"],
                attribution_score=float(row["attribution_score"]),
            )
        claims.append(
            ClaimDetail(
                id=row["id"],
                claim_text=row["claim_text"],
                claim_index=row["claim_index"],
                attribution=attribution,
                faithfulness_verdict=row["faithfulness_verdict"],
                faithfulness_score=float(row["faithfulness_score"]),
                is_faithful=row["is_faithful"],
                judge_reasoning=row["judge_reasoning"] or "",
            )
        )

    return TraceDetailResponse(
        id=trace_row["id"],
        query_text=trace_row["query_text"],
        llm_response=trace_row["llm_response"],
        status=trace_row["status"],
        latency_ms=trace_row["latency_ms"],
        created_at=trace_row["created_at"],
        claims=claims,
    )


@router.get("/projects/{project_id}/usage", response_model=UsageResponse)
async def get_usage(
    project_id: str,
    conn: asyncpg.Connection = Depends(get_db),
):
    if not await project_exists(conn, project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    today_row = await conn.fetchrow(
        """
        SELECT traces_ingested, traces_processed
        FROM usage_records
        WHERE project_id = $1::uuid AND date = CURRENT_DATE
        """,
        project_id,
    )

    day_rows = await conn.fetch(
        """
        SELECT date::text, traces_processed
        FROM usage_records
        WHERE project_id = $1::uuid AND date >= CURRENT_DATE - INTERVAL '6 days'
        ORDER BY date DESC
        """,
        project_id,
    )

    today_ingested = today_row["traces_ingested"] if today_row else 0
    today_processed = today_row["traces_processed"] if today_row else 0
    limit = settings.DAILY_PROCESSING_LIMIT

    return UsageResponse(
        today=UsageTodayItem(
            traces_ingested=today_ingested,
            traces_processed=today_processed,
            processing_limit=limit,
            limit_reached=today_processed >= limit,
        ),
        last_7_days=[
            UsageDayItem(date=r["date"], traces_processed=r["traces_processed"])
            for r in day_rows
        ],
    )


@router.get("/projects/{project_id}/clusters", response_model=ClustersResponse)
async def get_clusters(
    project_id: str,
    conn: asyncpg.Connection = Depends(get_db),
):
    if not await project_exists(conn, project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    rows = await conn.fetch(
        """
        SELECT id::text, cluster_label, avg_faithfulness, trace_count, unfaithful_count
        FROM query_clusters
        WHERE project_id = $1::uuid
        ORDER BY trace_count DESC
        """,
        project_id,
    )

    clusters = [
        QueryClusterItem(
            id=row["id"],
            label=row["cluster_label"],
            trace_count=row["trace_count"],
            avg_faithfulness=float(row["avg_faithfulness"]),
            # unfaithful_rate derived from stored avg: proportion of avg score that is unfaithful
            unfaithful_rate=round(1.0 - float(row["avg_faithfulness"]), 2),
        )
        for row in rows
    ]
    return ClustersResponse(clusters=clusters)


@router.get(
    "/projects/{project_id}/documents/problems",
    response_model=DocumentsProblemsResponse,
)
async def get_problem_documents(
    project_id: str,
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=20, ge=1, le=100),
    conn: asyncpg.Connection = Depends(get_db),
):
    if not await project_exists(conn, project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    # make_interval(days => $2) is the asyncpg-native way to parameterize an
    # INTERVAL with an integer — avoids string concatenation in SQL entirely.
    # Retrieval failures (null attributed_chunk_id) are excluded by the JOIN;
    # this view surfaces generation failures only (source found, AI misrepresented it).
    rows = await conn.fetch(
        """
        SELECT
            c.source_document,
            COUNT(*) AS total_claims,
            SUM(CASE WHEN cl.is_faithful = FALSE THEN 1 ELSE 0 END) AS unfaithful_claims,
            ROUND(AVG(cl.faithfulness_score)::numeric, 2) AS avg_faithfulness
        FROM claims cl
        JOIN chunks c ON cl.attributed_chunk_id = c.id
        WHERE c.project_id = $1::uuid
          AND cl.created_at > NOW() - make_interval(days => $2)
        GROUP BY c.source_document
        ORDER BY unfaithful_claims DESC
        LIMIT $3
        """,
        project_id,
        days,
        limit,
    )

    documents = []
    for row in rows:
        total = int(row["total_claims"])
        unfaithful = int(row["unfaithful_claims"])
        documents.append(
            DocumentProblemItem(
                source_document=row["source_document"],
                total_claims=total,
                unfaithful_claims=unfaithful,
                unfaithful_rate=round(unfaithful / total, 2) if total > 0 else 0.0,
                avg_faithfulness=float(row["avg_faithfulness"]),
            )
        )

    return DocumentsProblemsResponse(documents=documents)
