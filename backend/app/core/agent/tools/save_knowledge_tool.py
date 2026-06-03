"""将对话内容保存到个人知识库。"""

import logging
from typing import List

from .base import BaseTool, ToolResult, ToolStatus, ToolParameter
from app.models.schemas import KnowledgeCreate
from app.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)


class SaveKnowledgeTool(BaseTool):
    def __init__(self, db_session, tenant_id):
        self.db_session = db_session
        self.knowledge_service = KnowledgeService(db_session, tenant_id)

    @property
    def name(self) -> str:
        return "save_knowledge"

    @property
    def description(self) -> str:
        return "将标题与正文保存到个人知识库（来源标记为 agent）"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="title", type="string", description="知识标题", required=True
            ),
            ToolParameter(
                name="content", type="string", description="知识正文", required=True
            ),
            ToolParameter(
                name="tags",
                type="array",
                description="标签列表",
                required=False,
            ),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        title = (kwargs.get("title") or "").strip()
        content = (kwargs.get("content") or "").strip()
        tags = kwargs.get("tags")

        if not title or not content:
            return ToolResult(
                status=ToolStatus.FAILED,
                error="需要 title 与 content 参数",
            )

        try:
            knowledge = await self.knowledge_service.create(
                KnowledgeCreate(
                    title=title[:500],
                    content=content,
                    source_type="agent",
                    tags=tags or ["agent"],
                    metadata={"saved_via": "agent_tool"},
                )
            )
            return ToolResult(
                status=ToolStatus.SUCCESS,
                data={
                    "knowledge_id": str(knowledge.id),
                    "title": knowledge.title,
                },
            )
        except Exception as e:
            logger.error("save_knowledge failed: %s", e)
            return ToolResult(status=ToolStatus.FAILED, error=str(e))
