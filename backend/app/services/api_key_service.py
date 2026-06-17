import hashlib
import secrets
from typing import Optional

import asyncpg


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def create_api_key(
    conn: asyncpg.Connection,
    project_id: str,
    name: str,
) -> dict:
    raw_key = "cl_" + secrets.token_urlsafe(32)
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:16]

    row = await conn.fetchrow(
        """
        INSERT INTO api_keys (project_id, key_hash, key_prefix, name)
        VALUES ($1::uuid, $2, $3, $4)
        RETURNING id::text, name
        """,
        project_id,
        key_hash,
        key_prefix,
        name,
    )
    return {
        "id": row["id"],
        "name": row["name"],
        "key": raw_key,
        "key_prefix": key_prefix,
    }


async def list_api_keys(conn: asyncpg.Connection, project_id: str) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT id::text, name, key_prefix, last_used_at, revoked_at, created_at
        FROM api_keys
        WHERE project_id = $1::uuid
        ORDER BY created_at DESC
        """,
        project_id,
    )
    return [dict(r) for r in rows]


async def revoke_api_key(
    conn: asyncpg.Connection,
    project_id: str,
    key_id: str,
) -> bool:
    result = await conn.execute(
        """
        UPDATE api_keys SET revoked_at = NOW()
        WHERE id = $1::uuid AND project_id = $2::uuid AND revoked_at IS NULL
        """,
        key_id,
        project_id,
    )
    return result == "UPDATE 1"


async def get_project_from_key(
    conn: asyncpg.Connection,
    raw_key: str,
) -> Optional[str]:
    key_hash = _hash_key(raw_key)
    row = await conn.fetchrow(
        """
        SELECT id::text, project_id::text, revoked_at
        FROM api_keys
        WHERE key_hash = $1
        """,
        key_hash,
    )
    if not row or row["revoked_at"] is not None:
        return None
    await conn.execute(
        "UPDATE api_keys SET last_used_at = NOW() WHERE id = $1::uuid",
        row["id"],
    )
    return row["project_id"]
