"""
线上 Embedding 服务客户端。

通过硅基流动 OpenAI 兼容接口调用 BGE 模型，将文本转为 1024 维向量，
供 knowledge 入库与语义检索使用。配置见 app.core.config.settings。
"""

import httpx
import asyncio
from typing import List, Optional
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """令牌桶限流器，避免触发 Embedding API 的 QPS 限制。"""

    def __init__(self, rate: float = 10, per: float = 1.0):
        self.rate = rate  # 每个 per 秒允许的最大请求数
        self.per = per  # 每个请求的间隔时间
        self.tokens = rate  # 令牌数量
        self.last_refill = asyncio.get_event_loop().time()  # 上次令牌补给时间
        self.lock = asyncio.Lock()  # 锁，避免多个协程同时访问

    async def acquire(self):
        """获取一个令牌；不足时异步等待后重试。"""
        async with self.lock:
            now = asyncio.get_event_loop().time()  # 当前时间
            elapsed = now - self.last_refill  # 时间间隔
            self.tokens = min(self.rate, self.tokens + elapsed * self.rate)  # 令牌数量
            self.last_refill = now  # 上次令牌补给时间

            if self.tokens >= 1:
                self.tokens -= 1
                return True
            else:
                wait_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                return await self.acquire()


class OnlineEmbeddings:
    """硅基流动 Embedding API 的异步封装。"""

    def __init__(self, model: Optional[str] = None, max_retries: int = 3):
        self.api_key = settings.embedding_api_key
        self.base_url = settings.embedding_base_url
        self.model = model or settings.embedding_model
        self.timeout = 30.0
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(rate=10)  # 每秒最多 10 次请求

        if not self.api_key:
            logger.warning("EMBEDDING_API_KEY not set, embeddings will fail!")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
    )
    async def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """单批次向量化；网络/5xx 错误时指数退避重试。"""

        await self.rate_limiter.acquire()
        # 使用 httpx 异步客户端发送请求，避免阻塞当前协程
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": texts,
                    "encoding_format": "float",
                },
            )
            response.raise_for_status()
            data = response.json()

            # API 返回顺序可能与 input 不一致，按 index 排序后对齐
            embeddings = []
            for item in sorted(data["data"], key=lambda x: x["index"]):
                embeddings.append(item["embedding"])

            return embeddings

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """批量向量化，超出 API 批次上限时自动切分。"""

        if not texts:
            return []

        batch_size = 32  # BGE 模型单次 input 上限
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            logger.debug(
                f"Embedding batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}, size={len(batch)}"
            )

            embeddings = await self._embed_batch(batch)
            all_embeddings.extend(embeddings)

        return all_embeddings

    async def embed_query(self, query: str) -> List[float]:
        """检索场景：单条 query 转向量（Redis 缓存命中则跳过 API）。"""
        from app.core.cache import CacheService, cache_key, hash_text
        from app.core.config import settings

        normalized = query.strip()
        if normalized:
            ck = cache_key("emb", hash_text(f"{self.model}:{normalized}"))
            cached = await CacheService.get_json(ck)
            if isinstance(cached, list) and cached:
                return cached

        vector = (await self.embed([query]))[0]

        if normalized:
            await CacheService.set_json(ck, vector, settings.cache_ttl_embedding)
        return vector

    async def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """入库场景：批量文档转向量。"""
        return await self.embed(documents)


# 进程内共享实例，避免重复创建 HTTP 客户端配置
embeddings_service = OnlineEmbeddings()
