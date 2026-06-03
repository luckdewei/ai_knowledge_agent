"""
Agent 记忆服务：短期（会话）、长期、情景记忆，按租户隔离。
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.llm import Message, MessageRole, get_llm
from app.models.knowledge import AgentMemory

logger = logging.getLogger(__name__)

MEMORY_TYPE_LABELS = {
    "short_term": "短期",
    "long_term": "长期",
    "episodic": "情景",
}


class MemoryService:
    def __init__(
        self,
        db_session: AsyncSession,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
    ):
        self.db = db_session
        self.tenant_id = tenant_id
        self.user_id = user_id

    def _base_filters(self):
        return [AgentMemory.tenant_id == self.tenant_id]

    async def add_memory(
        self,
        content: str,
        memory_type: str = "long_term",
        context: Optional[Dict] = None,
        importance_score: float = 0.5,
        ttl_hours: Optional[int] = None,
    ) -> AgentMemory:
        ctx = dict(context or {})
        if "session_id" not in ctx:
            ctx.setdefault("session_id", "default")

        memory = AgentMemory(
            id=uuid.uuid4(),
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            memory_type=memory_type,
            content=content.strip(),
            context=ctx,
            importance_score=importance_score,
            expires_at=(
                datetime.now() + timedelta(hours=ttl_hours) if ttl_hours else None
            ),
        )
        self.db.add(memory)
        await self.db.commit()
        await self.db.refresh(memory)
        logger.info("Added %s memory for tenant %s", memory_type, self.tenant_id)
        return memory

    async def list_memories(
        self,
        *,
        memory_type: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> List[AgentMemory]:
        filters = self._base_filters()
        if memory_type:
            filters.append(AgentMemory.memory_type == memory_type)
        if session_id:
            filters.append(AgentMemory.context["session_id"].astext == session_id)

        stmt = (
            select(AgentMemory)
            .where(and_(*filters))
            .order_by(AgentMemory.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete_memory(self, memory_id: uuid.UUID) -> bool:
        stmt = select(AgentMemory).where(
            AgentMemory.id == memory_id,
            AgentMemory.tenant_id == self.tenant_id,
        )
        result = await self.db.execute(stmt)
        memory = result.scalar_one_or_none()
        if not memory:
            return False
        await self.db.delete(memory)
        await self.db.commit()
        return True

    async def get_relevant_memories(
        self,
        query: str,
        session_id: str = "default",
        limit: int = 5,
        include_long_term: bool = True,
    ) -> List[AgentMemory]:
        memories: list[AgentMemory] = []
        now = datetime.now()

        short_stmt = (
            select(AgentMemory)
            .where(
                and_(
                    *self._base_filters(),
                    AgentMemory.memory_type == "short_term",
                    AgentMemory.context["session_id"].astext == session_id,
                    or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > now),
                )
            )
            .order_by(AgentMemory.created_at.desc())
            .limit(limit)
        )
        short_result = await self.db.execute(short_stmt)
        memories.extend(short_result.scalars().all())

        if include_long_term:
            long_stmt = (
                select(AgentMemory)
                .where(
                    and_(
                        *self._base_filters(),
                        AgentMemory.memory_type.in_(("long_term", "episodic")),
                        or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > now),
                    )
                )
                .order_by(
                    AgentMemory.importance_score.desc(),
                    AgentMemory.created_at.desc(),
                )
                .limit(limit)
            )
            long_result = await self.db.execute(long_stmt)
            memories.extend(long_result.scalars().all())

        seen: set[uuid.UUID] = set()
        unique: list[AgentMemory] = []
        for m in memories:
            if m.id not in seen:
                seen.add(m.id)
                unique.append(m)
        return unique[:limit]

    async def get_memory_context(
        self, session_id: str, query: str, limit: int = 5
    ) -> Dict[str, Any]:
        memories = await self.get_relevant_memories(
            query=query, session_id=session_id, limit=limit
        )
        short_count = len(
            await self.list_memories(memory_type="short_term", session_id=session_id, limit=100)
        )
        return {
            "session_id": session_id,
            "short_term_count": short_count,
            "long_term_count": len(
                [m for m in memories if m.memory_type in ("long_term", "episodic")]
            ),
            "relevant_memories": [
                {
                    "id": str(m.id),
                    "memory_type": m.memory_type,
                    "content": m.content,
                    "importance": m.importance_score,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in memories
            ],
        }

    async def _content_exists(self, content: str, memory_type: str) -> bool:
        stmt = select(AgentMemory.id).where(
            and_(
                *self._base_filters(),
                AgentMemory.memory_type == memory_type,
                AgentMemory.content == content.strip(),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    def _parse_llm_memory_json(self, raw: str) -> list[dict]:
        text = (raw or "").strip()
        if not text:
            return []
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
        if data.get("skip") is True:
            return []
        items = data.get("memories")
        if not isinstance(items, list):
            return []
        return [x for x in items if isinstance(x, dict) and x.get("content")]

    async def llm_extract_and_save_memories(
        self,
        session_id: str,
        user_query: str,
        assistant_answer: str,
    ) -> list[AgentMemory]:
        """由 LLM 判断是否写入记忆及类型，无需用户手动操作。"""
        if not user_query.strip() or not assistant_answer.strip():
            return []

        llm = get_llm(fast=True)
        prompt = f"""你是记忆管理模块。根据下面一轮对话，判断是否有值得存入个人记忆库的信息。

只记录对**后续对话**有帮助的内容：用户身份/偏好/习惯、长期目标、项目背景、明确待办、重要结论。
不要记录：寒暄、通用知识问答、无个人信息的闲聊、助手已写在知识库里的内容。

用户问：
{user_query.strip()[:800]}

助手答：
{assistant_answer.strip()[:1200]}

仅输出 JSON（不要 markdown）：
{{
  "skip": false,
  "memories": [
    {{
      "memory_type": "long_term",
      "content": "用户主要使用 Python 做数据分析",
      "importance_score": 0.75
    }}
  ]
}}

memory_type 只能是 short_term（本会话上下文/待办）、long_term（跨会话偏好与事实）、episodic（重要事件/决策）。
若无值得记录的，输出 {{"skip": true, "memories": []}}。
每条 content 不超过 100 字，最多 3 条。"""

        saved: list[AgentMemory] = []
        try:
            resp = await llm.invoke([Message(role=MessageRole.USER, content=prompt)])
            candidates = self._parse_llm_memory_json(resp.content or "")
        except Exception as e:
            logger.warning("LLM memory extraction failed: %s", e)
            return []

        for item in candidates[:3]:
            mtype = str(item.get("memory_type", "long_term")).strip()
            if mtype not in ("short_term", "long_term", "episodic"):
                mtype = "long_term"
            content = str(item.get("content", "")).strip()
            if not content or len(content) < 4:
                continue
            if await self._content_exists(content, mtype):
                continue
            try:
                score = float(item.get("importance_score", 0.55))
            except (TypeError, ValueError):
                score = 0.55
            score = max(0.3, min(1.0, score))
            ttl = 72 if mtype == "short_term" else None
            mem = await self.add_memory(
                content=content[:500],
                memory_type=mtype,
                context={"session_id": session_id, "source": "llm_extract"},
                importance_score=score,
                ttl_hours=ttl,
            )
            saved.append(mem)
        return saved

    async def promote_to_long_term(
        self, memory_id: uuid.UUID, importance_score: float = 0.65
    ) -> AgentMemory | None:
        stmt = select(AgentMemory).where(
            AgentMemory.id == memory_id,
            AgentMemory.tenant_id == self.tenant_id,
        )
        result = await self.db.execute(stmt)
        src = result.scalar_one_or_none()
        if not src:
            return None
        return await self.add_memory(
            content=src.content,
            memory_type="long_term",
            context=src.context,
            importance_score=importance_score,
        )

    async def summarize_session(
        self, session_id: str, conversation: List[Dict[str, str]]
    ) -> str:
        if not conversation:
            return ""

        llm = get_llm(fast=True)
        prompt = f"""请总结以下对话的关键信息，提取需要长期记住的内容（用户偏好、重要结论、待办）。

对话：
{json.dumps(conversation, ensure_ascii=False, indent=2)}

用简洁中文条目总结："""

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await llm.invoke(messages)
            summary = (response.content or "").strip()
            if summary:
                await self.add_memory(
                    content=summary[:800],
                    memory_type="episodic",
                    context={
                        "session_id": session_id,
                        "conversation_length": len(conversation),
                    },
                    importance_score=0.65,
                )
            return summary
        except Exception as e:
            logger.error("Session summarization failed: %s", e)
            return ""

    async def forget_expired_memories(self) -> int:
        stmt = select(AgentMemory).where(
            and_(
                *self._base_filters(),
                AgentMemory.expires_at.isnot(None),
                AgentMemory.expires_at <= datetime.now(),
            )
        )
        result = await self.db.execute(stmt)
        expired = result.scalars().all()
        for memory in expired:
            await self.db.delete(memory)
        if expired:
            await self.db.commit()
        return len(expired)
