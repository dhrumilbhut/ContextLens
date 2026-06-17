import redis.asyncio as aioredis

from app.config import settings

_redis: aioredis.Redis | None = None


async def create_connection() -> None:
    global _redis
    _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def close_connection() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


async def get_redis() -> aioredis.Redis:
    return _redis
