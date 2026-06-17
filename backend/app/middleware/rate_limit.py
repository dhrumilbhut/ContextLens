import time

import redis.asyncio as aioredis

from app.config import settings


class RateLimitError(Exception):
    pass


async def check_rate_limits(redis: aioredis.Redis, project_id: str) -> None:
    now = time.time()

    minute_key = f"ratelimit:{project_id}:minute:{int(now // 60)}"
    minute_count = await redis.incr(minute_key)
    await redis.expire(minute_key, 120)
    if minute_count > settings.PER_MINUTE_RATE_LIMIT:
        raise RateLimitError("Rate limit exceeded: too many requests per minute")

    hour_key = f"ratelimit:{project_id}:hour:{int(now // 3600)}"
    hour_count = await redis.incr(hour_key)
    await redis.expire(hour_key, 7200)
    if hour_count > settings.HOURLY_INGEST_RATE_LIMIT:
        raise RateLimitError("Rate limit exceeded: too many requests per hour")
