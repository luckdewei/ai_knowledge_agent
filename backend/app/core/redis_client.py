"""Redis 异步客户端（可选依赖，连接失败时降级为无缓存）。"""

import logging
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None
_available: bool = False


async def init_redis() -> bool:
    """应用启动时连接 Redis。"""
    global _redis, _available

    if not settings.redis_enabled:
        logger.info("Redis disabled by config (REDIS_ENABLED=false)")
        _available = False
        return False

    try:
        client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await client.ping()
        _redis = client
        _available = True
        logger.info("Redis connected: %s", settings.redis_url.split("@")[-1])
        return True
    except Exception as e:
        _redis = None
        _available = False
        logger.warning("Redis unavailable, running without cache: %s", e)
        return False


async def close_redis() -> None:
    global _redis, _available
    if _redis is not None:
        await _redis.aclose()
    _redis = None
    _available = False


def get_redis() -> Optional[aioredis.Redis]:
    return _redis if _available else None


def redis_available() -> bool:
    return _available and _redis is not None


async def redis_ping() -> bool:
    if not redis_available():
        return False
    try:
        assert _redis is not None
        return bool(await _redis.ping())
    except Exception:
        return False
