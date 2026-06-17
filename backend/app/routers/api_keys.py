import asyncpg
from fastapi import APIRouter, Depends, HTTPException

from app.database import get_db
from app.models.api_keys import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyListItem,
    ApiKeyListResponse,
)
from app.services.api_key_service import create_api_key, list_api_keys, revoke_api_key
from app.services.project_service import project_exists

router = APIRouter()


@router.post(
    "/projects/{project_id}/api-keys",
    status_code=201,
    response_model=ApiKeyCreateResponse,
)
async def post_api_key(
    project_id: str,
    body: ApiKeyCreate,
    conn: asyncpg.Connection = Depends(get_db),
):
    if not await project_exists(conn, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    key_data = await create_api_key(conn, project_id, body.name)
    return ApiKeyCreateResponse(
        id=key_data["id"],
        name=key_data["name"],
        key=key_data["key"],
        key_prefix=key_data["key_prefix"],
    )


@router.get("/projects/{project_id}/api-keys", response_model=ApiKeyListResponse)
async def get_api_keys(
    project_id: str,
    conn: asyncpg.Connection = Depends(get_db),
):
    if not await project_exists(conn, project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    keys = await list_api_keys(conn, project_id)
    items = [
        ApiKeyListItem(
            id=k["id"],
            name=k["name"],
            key_prefix=k["key_prefix"],
            last_used_at=k["last_used_at"],
            revoked_at=k["revoked_at"],
            created_at=k["created_at"],
        )
        for k in keys
    ]
    return ApiKeyListResponse(api_keys=items)


@router.delete("/projects/{project_id}/api-keys/{key_id}")
async def delete_api_key(
    project_id: str,
    key_id: str,
    conn: asyncpg.Connection = Depends(get_db),
):
    revoked = await revoke_api_key(conn, project_id, key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"message": "API key revoked."}
