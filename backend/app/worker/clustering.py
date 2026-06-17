"""
k-means query clustering for ContextLens.

Groups semantically similar queries per project and labels each cluster using
an LLM. Results are fully recomputed on each run (DELETE + INSERT — not incremental).

Called by scheduled_tasks.cluster_project_queries_all every 6 hours.
"""

import logging

import asyncpg
import numpy as np
from openai import AsyncOpenAI
from sklearn.cluster import KMeans

from app.config import settings
from app.worker.embedder import embed_texts

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def _vec_to_str(vec: list) -> str:
    return "[" + ",".join(str(x) for x in vec) + "]"


def _parse_vector(vec_str: str) -> list[float]:
    return [float(x) for x in vec_str.strip("[]").split(",")]


CLUSTER_LABEL_PROMPT = """You are given a list of user queries sent to an AI assistant.
These queries were grouped together because they are semantically similar.

Write a short label (3-6 words) that describes what topic these queries share.
The label should be lowercase and descriptive, like:
  "questions about billing and refunds"
  "shipping and delivery questions"
  "account login and password issues"

Queries:
{queries}

Return only the label string. Nothing else."""


async def _label_cluster(sample_queries: list[str]) -> str:
    queries_text = "\n".join(f"- {q}" for q in sample_queries)
    result = await _get_client().chat.completions.create(
        model=settings.CONTEXTLENS_DECOMPOSE_MODEL,
        messages=[{
            "role": "user",
            "content": CLUSTER_LABEL_PROMPT.format(queries=queries_text),
        }],
    )
    return result.choices[0].message.content.strip().strip('"')


async def _backfill_query_embeddings(conn: asyncpg.Connection, project_id: str) -> None:
    """Embed query_text for processed traces that predate the query_embedding fix."""
    rows = await conn.fetch(
        """
        SELECT id::text, query_text
        FROM traces
        WHERE project_id = $1::uuid
          AND status = 'processed'
          AND query_embedding IS NULL
        """,
        project_id,
    )
    if not rows:
        return

    texts = [r["query_text"] for r in rows]
    embeddings = await embed_texts(texts)
    for row, emb in zip(rows, embeddings):
        await conn.execute(
            "UPDATE traces SET query_embedding = $1::vector WHERE id = $2::uuid",
            _vec_to_str(emb),
            row["id"],
        )
    logger.info(
        f"project {project_id}: backfilled query_embedding for {len(rows)} traces"
    )


async def cluster_project_queries(conn: asyncpg.Connection, project_id: str) -> None:
    """Run k-means on all query embeddings for a project. Full recompute each run."""
    await _backfill_query_embeddings(conn, project_id)

    rows = await conn.fetch(
        """
        SELECT id::text, query_text, query_embedding::text AS query_embedding_str
        FROM traces
        WHERE project_id = $1::uuid
          AND status = 'processed'
          AND query_embedding IS NOT NULL
        """,
        project_id,
    )

    if len(rows) < settings.CLUSTERING_MIN_TRACES:
        logger.info(
            f"project {project_id}: {len(rows)} traces < min {settings.CLUSTERING_MIN_TRACES} "
            f"— skipping clustering"
        )
        return

    embeddings = np.array([_parse_vector(r["query_embedding_str"]) for r in rows])
    trace_ids = [r["id"] for r in rows]
    query_texts_all = [r["query_text"] for r in rows]

    k = min(settings.CLUSTERING_K, max(2, len(rows) // 15))
    logger.info(f"project {project_id}: clustering {len(rows)} traces into k={k}")

    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(embeddings)

    # Group indices by cluster label
    cluster_indices: dict[int, list[int]] = {}
    for i, lbl in enumerate(labels):
        cluster_indices.setdefault(int(lbl), []).append(i)

    # Full recompute: delete existing clusters first
    await conn.execute(
        "DELETE FROM query_clusters WHERE project_id = $1::uuid",
        project_id,
    )

    for cluster_idx, indices in cluster_indices.items():
        centroid = kmeans.cluster_centers_[cluster_idx]
        sample_q = [query_texts_all[i] for i in indices[:10]]
        c_trace_ids = [trace_ids[i] for i in indices]

        label_str = await _label_cluster(sample_q)

        stats_row = await conn.fetchrow(
            """
            SELECT
                COUNT(DISTINCT t.id)::int AS trace_count,
                COALESCE(AVG(cl.faithfulness_score), 1.0)::float AS avg_faithfulness,
                COALESCE(SUM(CASE WHEN cl.is_faithful = FALSE THEN 1 ELSE 0 END), 0)::int
                    AS unfaithful_count
            FROM traces t
            LEFT JOIN claims cl ON cl.trace_id = t.id
            WHERE t.id::text = ANY($1)
            """,
            c_trace_ids,
        )

        await conn.execute(
            """
            INSERT INTO query_clusters
              (project_id, cluster_label, centroid_embedding,
               avg_faithfulness, trace_count, unfaithful_count, updated_at)
            VALUES ($1::uuid, $2, $3::vector, $4, $5, $6, NOW())
            """,
            project_id,
            label_str,
            _vec_to_str(centroid.tolist()),
            float(stats_row["avg_faithfulness"]),
            len(c_trace_ids),
            int(stats_row["unfaithful_count"]),
        )

        logger.info(
            f"project {project_id}: cluster '{label_str}' — {len(c_trace_ids)} traces"
        )

    logger.info(f"project {project_id}: clustering complete, {k} clusters written")
