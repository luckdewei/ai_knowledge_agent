"""
搜索工具

支持网络搜索和知识库搜索
"""

import logging
from typing import Dict, List

import httpx

from .base import BaseTool, ToolResult, ToolStatus, ToolParameter
from app.core.config import settings
from app.services.knowledge_service import KnowledgeService
from app.models.schemas import SearchRequest

logger = logging.getLogger(__name__)


class SearchTool(BaseTool):
    """搜索工具"""

    def __init__(self, db_session=None):
        self.db_session = db_session
        self.knowledge_service = KnowledgeService(db_session) if db_session else None

    @property
    def name(self) -> str:
        return "search"

    @property
    def description(self) -> str:
        return "搜索网络信息或知识库，支持多种搜索源"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="query", type="string", description="搜索查询", required=True
            ),
            ToolParameter(
                name="source",
                type="string",
                description="搜索源: web, knowledge, both",
                required=False,
                default="both",
            ),
            ToolParameter(
                name="top_k",
                type="number",
                description="返回结果数量",
                required=False,
                default=5,
            ),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        """执行搜索"""
        query = kwargs.get("query")
        source = kwargs.get("source", "both")
        top_k = kwargs.get("top_k", 5)

        if not query:
            return ToolResult(
                status=ToolStatus.FAILED, error="Missing required parameter: query"
            )

        results = {"web": [], "knowledge": []}

        # 知识库搜索
        if source in ["knowledge", "both"] and self.knowledge_service:
            knowledge_results = await self._search_knowledge(query, top_k)
            results["knowledge"] = knowledge_results

        # 网络搜索
        if source in ["web", "both"]:
            web_results = await self._search_web(query, top_k)
            results["web"] = web_results

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=results,
            metadata={"query": query, "source": source},
        )

    async def _search_knowledge(self, query: str, top_k: int) -> list:
        """知识库搜索"""
        if not self.knowledge_service:
            return []

        search_request = SearchRequest(query=query, top_k=top_k, min_similarity=0.5)
        results, _ = await self.knowledge_service.search_semantic(search_request)

        return [
            {
                "type": "knowledge",
                "title": k.title,
                "content": k.content[:300],
                "similarity": score,
                "source_type": k.source_type,
            }
            for k, score in results
        ]

    async def _search_web(self, query: str, top_k: int) -> list:
        """网络搜索"""
        # 使用 Tavily API 或自定义搜索
        tavily_key = settings.tavily_api_key

        if not tavily_key:
            logger.warning("TAVILY_API_KEY not set, using mock results")
            return self._mock_web_search(query, top_k)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": tavily_key,
                        "query": query,
                        "search_depth": "basic",
                        "max_results": top_k,
                    },
                )
                response.raise_for_status()
                data = response.json()

                return [
                    {
                        "type": "web",
                        "title": r.get("title"),
                        "url": r.get("url"),
                        "content": r.get("content")[:300],
                        "score": r.get("score"),
                    }
                    for r in data.get("results", [])
                ]
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return self._mock_web_search(query, top_k)

    def _mock_web_search(self, query: str, top_k: int) -> list:
        """模拟搜索结果（用于测试）"""
        return [
            {
                "type": "web",
                "title": f"关于 {query} 的搜索结果 {i+1}",
                "url": f"https://example.com/result/{i+1}",
                "content": f"这是关于 {query} 的模拟搜索结果内容...",
                "score": 1.0 - i * 0.1,
            }
            for i in range(min(top_k, 3))
        ]
