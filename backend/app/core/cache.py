"""基于 Redis 的 JSON / 字符串缓存，未连接 Redis 时透明降级。"""

import hashlib
import json
import logging
import uuid
from typing import Any, Optional, Union

from app.core.redis_client import get_redis, redis_available

logger = logging.getLogger(__name__)

KEY_PREFIX = "pka"


def cache_key(*parts: Any) -> str:
    """Build a Redis key; all segments are coerced to str (e.g. UUID from asyncpg)."""
    return ":".join([KEY_PREFIX, *(str(p) for p in parts)])


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CacheService:
    @staticmethod
    async def get(key: str) -> Optional[str]:
        client = get_redis()
        if not client:
            return None
        try:
            return await client.get(key)
        except Exception as e:
            logger.debug("Cache get failed %s: %s", key, e)
            return None

    @staticmethod
    async def set(key: str, value: str, ttl: int) -> None:
        client = get_redis()
        if not client:
            return
        try:
            await client.setex(key, ttl, value)
        except Exception as e:
            logger.debug("Cache set failed %s: %s", key, e)

    @staticmethod
    async def get_json(key: str) -> Optional[Any]:
        raw = await CacheService.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    @staticmethod
    async def set_json(key: str, value: Any, ttl: int) -> None:
        await CacheService.set(key, json.dumps(value, ensure_ascii=False), ttl)

    @staticmethod
    async def delete(key: str) -> None:
        client = get_redis()
        if not client:
            return
        try:
            await client.delete(key)
        except Exception as e:
            logger.debug("Cache delete failed %s: %s", key, e)

    @staticmethod
    async def invalidate_prefix(prefix: str) -> int:
        """删除某前缀下的键，用于知识库变更后失效缓存。"""
        client = get_redis()
        if not client:
            return 0
        pattern = f"{prefix}*"
        deleted = 0
        try:
            async for key in client.scan_iter(match=pattern, count=100):
                await client.delete(key)
                deleted += 1
        except Exception as e:
            logger.debug("Cache invalidate failed %s: %s", pattern, e)
        return deleted


async def invalidate_knowledge_caches(
    tenant_id: Union[str, uuid.UUID, None] = None,
) -> None:
    """知识写入后失效统计、看板趋势与检索缓存。"""
    tid = str(tenant_id) if tenant_id else ""
    await CacheService.delete(cache_key("stats", "knowledge", tid))
    await CacheService.invalidate_prefix(cache_key("insights", tid) + ":")
    await CacheService.invalidate_prefix(cache_key("search", tid) + ":")


def cache_status() -> dict[str, Any]:
    return {"enabled": redis_available(), "prefix": KEY_PREFIX}
