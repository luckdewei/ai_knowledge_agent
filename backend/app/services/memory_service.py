"""
Agent 记忆服务

管理 Agent 的短期和长期记忆：
- 短期记忆：会话内的上下文
- 长期记忆：跨会话的重要信息
- 情景记忆：特定事件和决策
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json
import uuid

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import AgentMemory
from app.core.agent.llm import get_llm, Message, MessageRole

logger = logging.getLogger(__name__)


class MemoryService:
    """记忆服务"""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.session_memories = {}  # 短期记忆缓存

    async def add_memory(
        self,
        content: str,
        memory_type: str = "long_term",
        context: Optional[Dict] = None,
        importance_score: float = 0.5,
        ttl_hours: Optional[int] = None,
    ) -> AgentMemory:
        """
        添加记忆

        Args:
            content: 记忆内容
            memory_type: short_term, long_term, episodic
            context: 上下文信息
            importance_score: 重要程度 0-1
            ttl_hours: 过期时间（仅短期记忆）
        """
        memory = AgentMemory(
            id=uuid.uuid4(),
            memory_type=memory_type,
            content=content,
            context=context or {},
            importance_score=importance_score,
            expires_at=(
                datetime.now() + timedelta(hours=ttl_hours) if ttl_hours else None
            ),
        )

        self.db.add(memory)
        await self.db.commit()
        await self.db.refresh(memory)

        # 更新缓存（短期记忆）
        if memory_type == "short_term":
            session_id = (context or {}).get("session_id", "default")
            if session_id not in self.session_memories:
                self.session_memories[session_id] = []
            self.session_memories[session_id].append(memory)

        logger.info(f"Added {memory_type} memory: {content[:50]}...")
        return memory

    async def get_relevant_memories(
        self,
        query: str,
        session_id: str = "default",
        limit: int = 5,
        include_long_term: bool = True,
    ) -> List[AgentMemory]:
        """
        获取相关的记忆

        结合短期记忆（缓存）和长期记忆（向量检索）
        """
        memories = []

        # 1. 短期记忆（从缓存获取）
        short_term = self.session_memories.get(session_id, [])
        # 过滤过期的
        short_term = [
            m
            for m in short_term
            if m.expires_at is None or m.expires_at > datetime.now()
        ]
        memories.extend(short_term[-limit:])  # 最近几条

        if not include_long_term:
            return memories

        # 2. 长期记忆（向量检索）
        from app.core.vector.embeddings import embeddings_service

        try:
            query_vec = await embeddings_service.embed_query(query)

            # 向量检索（需要在 AgentMemory 表上创建向量索引）
            # 这里简化为按重要程度和时效性排序
            stmt = (
                select(AgentMemory)
                .where(
                    and_(
                        AgentMemory.memory_type == "long_term",
                        AgentMemory.expires_at.is_(None),
                    )
                )
                .order_by(
                    AgentMemory.importance_score.desc(), AgentMemory.created_at.desc()
                )
                .limit(limit)
            )

            result = await self.db.execute(stmt)
            long_term = result.scalars().all()
            memories.extend(long_term)

        except Exception as e:
            logger.warning(f"Long-term memory retrieval failed: {e}")

        # 去重
        seen_ids = set()
        unique_memories = []
        for m in memories:
            if m.id not in seen_ids:
                seen_ids.add(m.id)
                unique_memories.append(m)

        return unique_memories[:limit]

    async def consolidate_memories(self):
        """
        记忆巩固

        将重要的短期记忆转化为长期记忆
        """
        # 获取所有短期记忆
        all_short_term = []
        for session_memories in self.session_memories.values():
            all_short_term.extend(session_memories)

        for memory in all_short_term:
            # 高重要性的记忆转为长期
            if memory.importance_score > 0.7:
                existing = await self._check_existing_long_term(memory.content)
                if not existing:
                    await self.add_memory(
                        content=memory.content,
                        memory_type="long_term",
                        context=memory.context,
                        importance_score=memory.importance_score * 0.8,
                    )
                    logger.info(f"Consolidated memory: {memory.content[:50]}...")

    async def _check_existing_long_term(self, content: str) -> bool:
        """检查是否已存在相似的长期记忆"""
        stmt = select(AgentMemory).where(
            and_(AgentMemory.memory_type == "long_term", AgentMemory.content == content)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def forget_expired_memories(self):
        """清理过期的记忆"""
        stmt = select(AgentMemory).where(AgentMemory.expires_at <= datetime.now())
        result = await self.db.execute(stmt)
        expired = result.scalars().all()

        for memory in expired:
            await self.db.delete(memory)

        await self.db.commit()
        logger.info(f"Forgot {len(expired)} expired memories")

    async def get_memory_context(self, session_id: str, query: str) -> Dict[str, Any]:
        """
        获取记忆上下文（供 Agent 使用）
        """
        memories = await self.get_relevant_memories(
            query=query, session_id=session_id, limit=5
        )

        context = {
            "session_id": session_id,
            "short_term_count": len(self.session_memories.get(session_id, [])),
            "long_term_count": len(
                [m for m in memories if m.memory_type == "long_term"]
            ),
            "relevant_memories": [
                {
                    "content": m.content,
                    "importance": m.importance_score,
                    "created_at": m.created_at.isoformat(),
                }
                for m in memories
            ],
        }

        return context

    async def summarize_session(
        self, session_id: str, conversation: List[Dict[str, str]]
    ) -> str:
        """
        总结会话并提取重要记忆
        """
        if not conversation:
            return ""

        llm = get_llm()
        prompt = f"""请总结以下对话的关键信息，提取需要长期记住的重要内容。

对话记录：
{json.dumps(conversation, ensure_ascii=False, indent=2)}

输出格式：
- 会话主题：
- 用户偏好：
- 关键决策：
- 待办事项：

总结："""

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await llm.invoke(messages)
            summary = response.content

            # 存储为情景记忆
            await self.add_memory(
                content=summary[:500],
                memory_type="episodic",
                context={
                    "session_id": session_id,
                    "conversation_length": len(conversation),
                },
                importance_score=0.6,
            )

            return summary

        except Exception as e:
            logger.error(f"Session summarization failed: {e}")
            return ""
