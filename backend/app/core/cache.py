import json
import hashlib
from typing import Any, Optional
import redis.asyncio as aioredis
from app.core.config import settings
import structlog

logger = structlog.get_logger()

_redis: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def make_cache_key(prefix: str, *args) -> str:
    content = ":".join(str(a) for a in args)
    h = hashlib.sha256(content.encode()).hexdigest()[:16]
    return f"{prefix}:{h}"


async def cache_get(key: str) -> Optional[Any]:
    r = await get_redis()
    try:
        val = await r.get(key)
        return json.loads(val) if val else None
    except Exception as e:
        logger.warning("cache_get_error", key=key, error=str(e))
        return None


async def cache_set(key: str, value: Any, ttl: int = settings.REDIS_TTL):
    r = await get_redis()
    try:
        await r.setex(key, ttl, json.dumps(value))
    except Exception as e:
        logger.warning("cache_set_error", key=key, error=str(e))


async def cache_invalidate_by_prefix(prefix: str):
    r = await get_redis()
    try:
        keys = await r.keys(f"{prefix}:*")
        if keys:
            await r.delete(*keys)
            logger.info("cache_invalidated", prefix=prefix, count=len(keys))
    except Exception as e:
        logger.warning("cache_invalidate_error", prefix=prefix, error=str(e))
