from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyCreateResponse(BaseModel):
    id: str
    name: str
    key: str
    key_prefix: str


class ApiKeyListItem(BaseModel):
    id: str
    name: str
    key_prefix: str
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime


class ApiKeyListResponse(BaseModel):
    api_keys: list[ApiKeyListItem]
