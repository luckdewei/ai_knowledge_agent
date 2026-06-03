"""
搜索工具

支持网络搜索和知识库搜索
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any

from .base import BaseTool, ToolResult, ToolStatus, ToolParameter
from .web_search import tavily_web_search
from app.services.knowledge_service import KnowledgeService
from app.models.schemas import SearchRequest

logger = logging.getLogger(__name__)

KB_SEMANTIC_TIMEOUT_SEC = 10.0
WEB_SEARCH_TIMEOUT_SEC = 22.0


class SearchTool(BaseTool):
    """搜索工具"""

    def __init__(self, db_session=None, tenant_id=None):
        self.db_session = db_session
        self.knowledge_service = (
            KnowledgeService(db_session, tenant_id)
            if db_session and tenant_id
            else None
        )

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

        web_error: Optional[str] = None
        if source in ["web", "both"]:
            web_results, web_error = await self._search_web(query, top_k)
            results["web"] = web_results

        meta = {"query": query, "source": source}
        if web_error:
            meta["web_error"] = web_error

        if source == "web" and web_error and not results["web"]:
            return ToolResult(
                status=ToolStatus.FAILED,
                data=results,
                error=web_error,
                metadata=meta,
            )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=results,
            metadata=meta,
        )

    async def _search_knowledge(self, query: str, top_k: int) -> list:
        """知识库搜索"""
        if not self.knowledge_service:
            return []

        search_request = SearchRequest(query=query, top_k=top_k, min_similarity=0.5)
        try:
            results, _ = await asyncio.wait_for(
                self.knowledge_service.search_semantic(search_request),
                timeout=KB_SEMANTIC_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            logger.warning("Knowledge semantic search timed out")
            return []

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

    async def _search_web(
        self, query: str, top_k: int
    ) -> Tuple[list, Optional[str]]:
        """网络搜索，返回 (结果列表, 错误信息)。"""
        from app.core.agent.knowledge_gap import optimize_web_query

        return await tavily_web_search(
            optimize_web_query(query), top_k, timeout=WEB_SEARCH_TIMEOUT_SEC
        )
