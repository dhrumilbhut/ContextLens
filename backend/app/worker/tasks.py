"""
Celery tasks for the ContextLens attribution pipeline.

process_trace is the only task in Phase 1.
It runs the full attribution pipeline: decompose → embed → attribute → judge.
"""

import asyncio
import json
import logging

import asyncpg

from celery.exceptions import MaxRetriesExceededError

from app.config import settings
from app.services.chunk_service import get_or_create_chunk
from app.services.trace_service import increment_usage, update_trace_status
from app.worker.attributor import attribute_claim
from app.worker.celery_app import celery_app
from app.worker.decomposer import decompose_claims
from app.worker.embedder import embed_texts
from app.worker.judge import score_faithfulness

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def process_trace(self, trace_id: str) -> None:
    try:
        asyncio.run(_run_pipeline(trace_id))
    except MaxRetriesExceededError:
        asyncio.run(_mark_failed(trace_id, "Max retries exceeded"))
    except Exception as exc:
        try:
            raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
        except MaxRetriesExceededError:
            asyncio.run(_mark_failed(trace_id, str(exc)))


async def _mark_failed(trace_id: str, error_message: str) -> None:
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        await update_trace_status(conn, trace_id, "failed", error_message)
        logger.error(f"trace {trace_id} | status: failed | {error_message}")
    finally:
        await conn.close()


async def _run_pipeline(trace_id: str) -> None:
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        await _process_trace(conn, trace_id)
    finally:
        await conn.close()


async def _process_trace(conn: asyncpg.Connection, trace_id: str) -> None:
    logger.info(f"picked up trace {trace_id}")

    # 1. Fetch trace
    row = await conn.fetchrow(
        """
        SELECT query_text, retrieved_chunks, llm_response, project_id
        FROM traces WHERE id = $1::uuid
        """,
        trace_id,
    )
    if not row:
        logger.warning(f"trace {trace_id} not found — skipping")
        return

    logger.info(f"trace {trace_id} | query: {row['query_text']}")

    # 2. Update status to processing
    await conn.execute(
        "UPDATE traces SET status = 'processing' WHERE id = $1::uuid",
        trace_id,
    )

    # retrieved_chunks is JSONB — asyncpg returns it as a Python list
    retrieved_chunks = row["retrieved_chunks"]
    if isinstance(retrieved_chunks, str):
        retrieved_chunks = json.loads(retrieved_chunks)

    project_id = str(row["project_id"]) if row["project_id"] is not None else None

    # 3. Decompose response into atomic claims
    claims = await decompose_claims(row["llm_response"])
    logger.info(f"trace {trace_id} | decomposed into {len(claims)} claims")

    if not claims:
        await conn.execute(
            "UPDATE traces SET status = 'processed' WHERE id = $1::uuid",
            trace_id,
        )
        return

    # 4. Batch embed query + claims + chunk contents in one API call.
    # query_text is prepended so its embedding is stored for clustering.
    chunk_texts = [c["content"] for c in retrieved_chunks]
    all_texts = [row["query_text"]] + claims + chunk_texts
    all_embeddings = await embed_texts(all_texts)
    query_embedding = all_embeddings[0]
    claim_embeddings = all_embeddings[1: 1 + len(claims)]
    chunk_embeddings = all_embeddings[1 + len(claims):]

    logger.info(f"trace {trace_id} | embedded {len(all_texts)} texts")

    # 4b. Store query embedding now — used by the clustering beat job.
    query_emb_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    await conn.execute(
        "UPDATE traces SET query_embedding = $1::vector WHERE id = $2::uuid",
        query_emb_str,
        trace_id,
    )

    # 5. Store chunks with deduplication, collect their DB UUIDs
    chunk_uuids: list[str] = []
    for i, chunk in enumerate(retrieved_chunks):
        chunk_id = await get_or_create_chunk(
            db=conn,
            content=chunk["content"],
            source=chunk["source"],
            chunk_index=chunk.get("chunk_index", i),
            embedding=chunk_embeddings[i],
            project_id=project_id,
        )
        chunk_uuids.append(chunk_id)

    logger.info(f"trace {trace_id} | stored {len(chunk_uuids)} chunks")

    # 6. Attribute and judge each claim
    for claim_index, (claim_text, claim_emb) in enumerate(
        zip(claims, claim_embeddings)
    ):
        chunk_idx, attribution_score = attribute_claim(claim_emb, chunk_embeddings)

        if chunk_idx is not None:
            attributed_chunk_id = chunk_uuids[chunk_idx]
            chunk_content = retrieved_chunks[chunk_idx]["content"]
            faith = await score_faithfulness(claim_text, chunk_content)
            # Include source_quote in judge_reasoning for dashboard auditability
            reasoning = (
                f'[source: "{faith["source_quote"]}"] {faith["reasoning"]}'
                if faith.get("source_quote")
                else faith["reasoning"]
            )
        else:
            attributed_chunk_id = None
            attribution_score = None
            faith = {
                "verdict": "unfaithful",
                "score": 0.0,
                "reasoning": "No source chunk found in retrieved context — retrieval failure.",
            }
            reasoning = faith["reasoning"]

        is_faithful = faith["verdict"] == "faithful"

        await conn.execute(
            """
            INSERT INTO claims (
                trace_id, claim_text, claim_index,
                attributed_chunk_id, attribution_score,
                faithfulness_verdict, faithfulness_score,
                is_faithful, judge_reasoning
            ) VALUES (
                $1::uuid, $2, $3,
                $4::uuid, $5,
                $6, $7,
                $8, $9
            )
            """,
            trace_id,
            claim_text,
            claim_index,
            attributed_chunk_id,
            attribution_score,
            faith["verdict"],
            faith["score"],
            is_faithful,
            reasoning,
        )

        attr_str = f"{attribution_score:.2f}" if attribution_score is not None else "none"
        logger.info(
            f"trace {trace_id} | claim {claim_index}: {faith['verdict']} (attribution={attr_str})"
        )

    # 7. Mark trace as processed
    await conn.execute(
        "UPDATE traces SET status = 'processed' WHERE id = $1::uuid",
        trace_id,
    )
    logger.info(f"trace {trace_id} | status: processed")

    # 8. Increment usage record — non-critical, never fail the task over this
    if project_id:
        try:
            await increment_usage(conn, project_id, processed=True)
        except Exception as usage_exc:
            logger.warning(f"trace {trace_id} | usage increment failed: {usage_exc}")
