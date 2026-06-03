"""Tavily 联网搜索（Agent 与 search 工具共用）。"""

import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT_SEC = 25.0


async def tavily_web_search(
    query: str, top_k: int = 5, *, timeout: float = DEFAULT_TIMEOUT_SEC
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """
    调用 Tavily Search API。

    Returns:
        (results, error): 成功时 error 为 None；失败时 results 为空且 error 为原因说明。
    """
    api_key = (settings.tavily_api_key or "").strip()
    if not api_key:
        return [], "未配置 TAVILY_API_KEY（请在 backend/.env 中设置）"

    payload = {
        "query": query,
        "search_depth": "basic",
        "max_results": min(max(top_k, 1), 20),
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                TAVILY_SEARCH_URL,
                headers=headers,
                json=payload,
            )
            if response.status_code == 401:
                return [], "Tavily API Key 无效或已过期（401）"
            if response.status_code == 432:
                return [], "Tavily 配额已用尽，请升级套餐（432）"
            if response.status_code >= 400:
                detail = response.text[:200]
                return [], f"Tavily 请求失败 HTTP {response.status_code}: {detail}"

            data = response.json()
            raw = data.get("results") or []
            if not raw:
                return [], "Tavily 返回 0 条结果"

            return [
                {
                    "type": "web",
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "content": (r.get("content") or "")[:300],
                    "score": r.get("score"),
                }
                for r in raw
            ], None
    except httpx.TimeoutException:
        logger.warning("Tavily search timed out (%.0fs): %s", timeout, query[:80])
        return [], f"联网搜索超时（>{timeout:.0f}s），请检查网络或稍后重试"
    except httpx.HTTPError as e:
        logger.error("Tavily HTTP error: %s", e)
        return [], f"联网搜索网络错误：{e}"
    except Exception as e:
        logger.error("Tavily search failed: %s", e)
        return [], f"联网搜索异常：{e}"
