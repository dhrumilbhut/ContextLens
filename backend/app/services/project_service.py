from typing import Optional

import asyncpg


async def create_project(
    conn: asyncpg.Connection,
    name: str,
    description: Optional[str] = None,
) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO projects (name, description)
        VALUES ($1, $2)
        RETURNING id::text, name, created_at
        """,
        name,
        description,
    )
    return dict(row)


async def list_projects(conn: asyncpg.Connection) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT
            p.id::text,
            p.name,
            p.description,
            p.created_at,
            COUNT(DISTINCT t.id) AS trace_count,
            AVG(c.faithfulness_score) AS avg_faithfulness
        FROM projects p
        LEFT JOIN traces t ON t.project_id = p.id
        LEFT JOIN claims c ON c.trace_id = t.id
        GROUP BY p.id
        ORDER BY p.created_at DESC
        """
    )
    return [dict(r) for r in rows]


async def get_project(conn: asyncpg.Connection, project_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        "SELECT id::text, name FROM projects WHERE id = $1::uuid",
        project_id,
    )
    if not row:
        return None

    stats_row = await conn.fetchrow(
        """
        SELECT
            COUNT(DISTINCT t.id) AS trace_count,
            AVG(c.faithfulness_score) FILTER (
                WHERE t.created_at > NOW() - INTERVAL '7 days'
            ) AS avg_faithfulness_7d,
            COUNT(c.id) FILTER (
                WHERE c.is_faithful = FALSE
                  AND t.created_at > NOW() - INTERVAL '7 days'
            ) AS unfaithful_count_7d,
            COUNT(c.id) FILTER (
                WHERE t.created_at > NOW() - INTERVAL '7 days'
            ) AS total_claims_7d
        FROM traces t
        LEFT JOIN claims c ON c.trace_id = t.id
        WHERE t.project_id = $1::uuid
        """,
        project_id,
    )

    doc_rows = await conn.fetch(
        """
        SELECT
            ch.source_document AS source,
            COUNT(cl.id) FILTER (WHERE cl.is_faithful = FALSE) AS unfaithful_claims
        FROM claims cl
        JOIN chunks ch ON cl.attributed_chunk_id = ch.id
        WHERE ch.project_id = $1::uuid
          AND cl.created_at > NOW() - INTERVAL '7 days'
        GROUP BY ch.source_document
        HAVING COUNT(cl.id) FILTER (WHERE cl.is_faithful = FALSE) > 0
        ORDER BY unfaithful_claims DESC
        LIMIT 3
        """,
        project_id,
    )

    total_7d = stats_row["total_claims_7d"] or 0
    unfaithful_7d = stats_row["unfaithful_count_7d"] or 0

    return {
        "id": row["id"],
        "name": row["name"],
        "trace_count": stats_row["trace_count"] or 0,
        "avg_faithfulness_7d": (
            float(stats_row["avg_faithfulness_7d"])
            if stats_row["avg_faithfulness_7d"] is not None
            else None
        ),
        "unfaithful_claim_rate": (
            round(unfaithful_7d / total_7d, 4) if total_7d > 0 else None
        ),
        "top_problem_documents": [
            {"source": r["source"], "unfaithful_claims": r["unfaithful_claims"]}
            for r in doc_rows
        ],
    }


async def project_exists(conn: asyncpg.Connection, project_id: str) -> bool:
    result = await conn.fetchval(
        "SELECT 1 FROM projects WHERE id = $1::uuid",
        project_id,
    )
    return result is not None


async def delete_project(conn: asyncpg.Connection, project_id: str) -> bool:
    result = await conn.execute(
        "DELETE FROM projects WHERE id = $1::uuid",
        project_id,
    )
    return result == "DELETE 1"
