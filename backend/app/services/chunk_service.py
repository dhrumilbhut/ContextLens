"""
Chunk deduplication and storage.

Chunks are deduplicated by content_hash (SHA256) within a project.
The same document chunk retrieved 1,000 times is stored once.

Phase 2: project_id is now NOT NULL. The Phase 1 manual SELECT+INSERT workaround
for NULL project_ids has been removed. ON CONFLICT works correctly for all rows.
"""

import hashlib

import asyncpg


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _embedding_to_str(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


async def get_or_create_chunk(
    db: asyncpg.Connection,
    content: str,
    source: str,
    chunk_index: int,
    embedding: list[float],
    project_id: str,
) -> str:
    """
    Returns the UUID (as string) of the chunk row, creating it if it doesn't exist.
    Deduplicates by content_hash within the project using ON CONFLICT.
    """
    content_hash = _content_hash(content)
    embedding_str = _embedding_to_str(embedding)

    chunk_id = await db.fetchval(
        """
        INSERT INTO chunks (project_id, content, content_hash, source_document, chunk_index, embedding)
        VALUES ($1::uuid, $2, $3, $4, $5, $6::vector)
        ON CONFLICT (project_id, content_hash) DO NOTHING
        RETURNING id::text
        """,
        project_id,
        content,
        content_hash,
        source,
        chunk_index,
        embedding_str,
    )
    if chunk_id is None:
        chunk_id = await db.fetchval(
            "SELECT id::text FROM chunks WHERE project_id = $1::uuid AND content_hash = $2",
            project_id,
            content_hash,
        )
    return chunk_id


async def store_chunk_embedding(
    db: asyncpg.Connection,
    chunk_id: str,
    embedding: list[float],
) -> None:
    """Updates the embedding on an existing chunk row."""
    embedding_str = _embedding_to_str(embedding)
    await db.execute(
        "UPDATE chunks SET embedding = $1::vector WHERE id = $2::uuid",
        embedding_str,
        chunk_id,
    )
