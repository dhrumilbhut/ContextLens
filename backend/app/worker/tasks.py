"""
Celery tasks for the ContextLens attribution pipeline.

process_trace runs the full attribution pipeline: decompose → embed → attribute → judge.

Changes in 0006 session:
  - attribute_claim now returns (chunk_idx, score, confidence) — 3-tuple
  - Low-confidence claims (0.65-0.75) get a real chunk_id and go through the judge
  - Refusal claims (is_refusal=True from decomposer) skip attribution and judge entirely
  - attribution_confidence column is now written for every claim
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

    retrieved_chunks = row["retrieved_chunks"]
    if isinstance(retrieved_chunks, str):
        retrieved_chunks = json.loads(retrieved_chunks)

    project_id = str(row["project_id"]) if row["project_id"] is not None else None

    # 3. Decompose response into atomic claims (now returns list[dict])
    claim_objects = await decompose_claims(row["llm_response"])
    logger.info(f"trace {trace_id} | decomposed into {len(claim_objects)} claims")

    if not claim_objects:
        await conn.execute(
            "UPDATE traces SET status = 'processed' WHERE id = $1::uuid",
            trace_id,
        )
        return

    # Separate refusal claims from factual claims that need embedding
    # Refusal claims skip embedding, attribution, and judging entirely.
    factual_claims = [c for c in claim_objects if not c["is_refusal"]]
    refusal_claims = [(i, c) for i, c in enumerate(claim_objects) if c["is_refusal"]]

    # 4. Batch embed query + factual claims + chunk contents in one API call.
    chunk_texts = [c["content"] for c in retrieved_chunks]
    factual_texts = [c["claim_text"] for c in factual_claims]
    all_texts = [row["query_text"]] + factual_texts + chunk_texts
    all_embeddings = await embed_texts(all_texts)
    query_embedding = all_embeddings[0]
    claim_embeddings = all_embeddings[1: 1 + len(factual_claims)]
    chunk_embeddings = all_embeddings[1 + len(factual_claims):]

    logger.info(f"trace {trace_id} | embedded {len(all_texts)} texts")

    # 4b. Store query embedding for clustering
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

    # 6. Process claims in original order.
    # Build a map from claim_object index → (claim_embedding index for factual claims)
    factual_iter = iter(enumerate(zip(factual_claims, claim_embeddings)))
    factual_emb_map: dict[int, tuple[dict, list[float]]] = {}
    fi = 0
    for obj_idx, claim_obj in enumerate(claim_objects):
        if not claim_obj["is_refusal"]:
            factual_emb_map[obj_idx] = (claim_obj, claim_embeddings[fi])
            fi += 1

    for claim_index, claim_obj in enumerate(claim_objects):
        claim_text = claim_obj["claim_text"]
        is_refusal = claim_obj["is_refusal"]

        if is_refusal:
            # Refusal claims: skip attribution and judge — store directly
            await conn.execute(
                """
                INSERT INTO claims (
                    trace_id, claim_text, claim_index,
                    attributed_chunk_id, attribution_score, attribution_confidence,
                    faithfulness_verdict, faithfulness_score,
                    is_faithful, judge_reasoning
                ) VALUES (
                    $1::uuid, $2, $3,
                    NULL, NULL, NULL,
                    'refusal', NULL,
                    NULL, $4
                )
                """,
                trace_id,
                claim_text,
                claim_index,
                "LLM correctly declined to answer — no relevant context was retrieved.",
            )
            logger.info(f"trace {trace_id} | claim {claim_index}: refusal (skipping attribution)")
            continue

        # Factual claim — attribute and judge
        claim_emb = factual_emb_map[claim_index][1]
        chunk_idx, attribution_score, confidence = attribute_claim(claim_emb, chunk_embeddings)

        if chunk_idx is not None:
            # Both 'high' and 'low' confidence claims get the judge
            attributed_chunk_id = chunk_uuids[chunk_idx]
            chunk_content = retrieved_chunks[chunk_idx]["content"]
            faith = await score_faithfulness(claim_text, chunk_content)
            reasoning = (
                f'[source: "{faith["source_quote"]}"] {faith["reasoning"]}'
                if faith.get("source_quote")
                else faith["reasoning"]
            )
            verdict = faith["verdict"]
            faith_score = faith["score"]
            is_faithful = verdict == "faithful"
        else:
            attributed_chunk_id = None
            attribution_score = None
            confidence = None
            verdict = "unfaithful"
            faith_score = 0.0
            is_faithful = False
            reasoning = "No source chunk found in retrieved context — retrieval failure."

        await conn.execute(
            """
            INSERT INTO claims (
                trace_id, claim_text, claim_index,
                attributed_chunk_id, attribution_score, attribution_confidence,
                faithfulness_verdict, faithfulness_score,
                is_faithful, judge_reasoning
            ) VALUES (
                $1::uuid, $2, $3,
                $4::uuid, $5, $6,
                $7, $8,
                $9, $10
            )
            """,
            trace_id,
            claim_text,
            claim_index,
            attributed_chunk_id,
            attribution_score,
            confidence,
            verdict,
            faith_score,
            is_faithful,
            reasoning,
        )

        attr_str = f"{attribution_score:.3f} ({confidence})" if attribution_score is not None else "none"
        logger.info(
            f"trace {trace_id} | claim {claim_index}: {verdict} (attribution={attr_str})"
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
