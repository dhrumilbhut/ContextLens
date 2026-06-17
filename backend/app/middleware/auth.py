import hashlib

import asyncpg
from fastapi import Depends, Header, HTTPException

from app.database import get_db


async def get_project_from_api_key(
    authorization: str = Header(...),
    conn: asyncpg.Connection = Depends(get_db),
) -> str:
    """Validates the Bearer key against the api_keys table. Returns project_id."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    raw_key = authorization[len("Bearer "):]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    row = await conn.fetchrow(
        """
        SELECT id::text, project_id::text, revoked_at
        FROM api_keys
        WHERE key_hash = $1
        """,
        key_hash,
    )
    if not row or row["revoked_at"] is not None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    await conn.execute(
        "UPDATE api_keys SET last_used_at = NOW() WHERE id = $1::uuid",
        row["id"],
    )
    return row["project_id"]
