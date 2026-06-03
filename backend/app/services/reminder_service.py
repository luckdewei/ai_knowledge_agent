"""
主动提醒服务

基于知识分析和时间条件主动提醒用户
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Knowledge
from app.services.trend_service import TrendAnalysisService
from app.services.recommendation_service import KnowledgeRecommendationService
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Reminder:
    """提醒内容"""

    id: str
    type: str  # review, connection, trend, milestone
    title: str
    content: str
    priority: int  # 1-5, 5最高
    created_at: datetime


class ActiveReminderService:
    """主动提醒服务"""

    def __init__(self, db_session: AsyncSession, tenant_id):
        import uuid as _uuid

        self.db = db_session
        self.tenant_id = (
            tenant_id
            if isinstance(tenant_id, _uuid.UUID)
            else _uuid.UUID(str(tenant_id))
        )
        from app.services.tenant_scope import tenant_knowledge_filter

        self._tk = tenant_knowledge_filter(self.tenant_id)
        self.trend_service = TrendAnalysisService(db_session)
        self.recommendation_service = KnowledgeRecommendationService(db_session)

    async def generate_reminders(self) -> List[Reminder]:
        """
        生成主动提醒

        包括：
        - 需要复习的知识（基于遗忘曲线）
        - 新发现的知识联系
        - 趋势变化提醒
        - 重要里程碑
        """
        reminders = []

        # 1. 复习提醒
        review_reminders = await self._generate_review_reminders()
        reminders.extend(review_reminders)

        # 2. 新联系提醒
        connection_reminders = await self._generate_connection_reminders()
        reminders.extend(connection_reminders)

        # 3. 趋势提醒
        trend_reminders = await self._generate_trend_reminders()
        reminders.extend(trend_reminders)

        # 4. 里程碑提醒
        milestone_reminders = await self._generate_milestone_reminders()
        reminders.extend(milestone_reminders)

        # 按优先级排序
        reminders.sort(key=lambda x: x.priority, reverse=True)

        return reminders

    async def _generate_review_reminders(self) -> List[Reminder]:
        """
        生成复习提醒

        基于艾宾浩斯遗忘曲线：
        - 1天后
        - 7天后
        - 30天后
        """
        reminders = []
        today = datetime.now().date()

        # 查询需要复习的知识
        review_intervals = [1, 7, 30]  # 天数

        for days in review_intervals:
            target_date = today - timedelta(days=days)
            target_start = datetime.combine(target_date, datetime.min.time())
            target_end = datetime.combine(target_date, datetime.max.time())

            stmt = (
                select(Knowledge).where(self._tk)
                .where(
                    and_(
                        Knowledge.created_at >= target_start,
                        Knowledge.created_at <= target_end,
                    )
                )
                .limit(5)
            )

            result = await self.db.execute(stmt)
            knowledge_list = result.scalars().all()

            for knowledge in knowledge_list:
                reminders.append(
                    Reminder(
                        id=f"review_{knowledge.id}_{days}",
                        type="review",
                        title=f"复习提醒：{knowledge.title}",
                        content=f"你 {days} 天前记录了这篇笔记，建议现在复习巩固。",
                        priority=3 if days <= 7 else 2,
                        created_at=datetime.now(),
                    )
                )

        return reminders

    async def _generate_connection_reminders(self) -> List[Reminder]:
        """
        生成新联系提醒

        发现最近创建的知识与已有知识的关联
        """
        reminders = []

        # 获取最近7天创建的知识
        week_ago = datetime.now() - timedelta(days=7)

        stmt = (
            select(Knowledge)
            .where(self._tk, Knowledge.created_at >= week_ago)
            .limit(10)
        )

        result = await self.db.execute(stmt)
        recent_knowledge = result.scalars().all()

        for knowledge in recent_knowledge:
            related = await self.recommendation_service.recommend_related(
                str(knowledge.id), limit=5
            )

            if related:
                reminders.append(
                    Reminder(
                        id=f"connection_{knowledge.id}",
                        type="connection",
                        title=f"发现新联系：{knowledge.title}",
                        content=f"你新记录的笔记与 {len(related)} 条已有知识相关。",
                        priority=4 if len(related) >= 3 else 2,
                        created_at=datetime.now(),
                    )
                )

        return reminders

    async def _generate_trend_reminders(self) -> List[Reminder]:
        """
        生成趋势提醒

        当某个主题突然变得活跃时提醒
        """
        reminders = []

        # 分析关注点变化
        attention_shift = await self.trend_service.analyze_attention_shift(days=30)

        # 上升主题提醒
        for tag_info in attention_shift.get("rising_tags", [])[:3]:
            if tag_info["change_percent"] > 50:  # 增长超过50%
                reminders.append(
                    Reminder(
                        id=f"trend_{tag_info['tag']}",
                        type="trend",
                        title=f"主题升温：{tag_info['tag']}",
                        content=f"过去30天，关于「{tag_info['tag']}」的关注度上升了 {tag_info['change_percent']:.0f}%。",
                        priority=3,
                        created_at=datetime.now(),
                    )
                )

        return reminders

    async def _generate_milestone_reminders(self) -> List[Reminder]:
        """
        生成里程碑提醒

        如：知识库达到100条、连续记录7天等
        """
        reminders = []

        # 统计总数
        total_stmt = select(func.count()).select_from(Knowledge)
        total = await self.db.execute(total_stmt)
        total_count = total.scalar() or 0

        # 里程碑检查
        milestones = [10, 50, 100, 500, 1000]
        for milestone in milestones:
            if total_count >= milestone and total_count - 10 < milestone:
                reminders.append(
                    Reminder(
                        id=f"milestone_{milestone}",
                        type="milestone",
                        title=f"🎉 知识库突破 {milestone} 条！",
                        content=f"恭喜！你的知识库已有 {total_count} 条笔记。继续加油！",
                        priority=5,
                        created_at=datetime.now(),
                    )
                )
                break

        return reminders

    async def get_personalized_insight(self, knowledge_id: str) -> Optional[str]:
        """
        生成个性化洞察

        例如："你去年记录的关于 Python 异步的想法，与你今天阅读的这篇文章观点一致"
        """
        # 获取当前知识
        stmt = select(Knowledge).where(self._tk, Knowledge.id == knowledge_id)
        result = await self.db.execute(stmt)
        current = result.scalar_one_or_none()

        if not current:
            return None

        # 查找相关的历史知识（时间较久远）
        old_date = datetime.now() - timedelta(days=365)

        related_stmt = (
            select(Knowledge)
            .where(and_(Knowledge.created_at <= old_date, Knowledge.id != knowledge_id))
            .limit(20)
        )

        related_result = await self.db.execute(related_stmt)
        old_knowledge = related_result.scalars().all()

        # 计算相似度
        from app.core.vector.embeddings import embeddings_service

        current_vec = self._get_vector(
            await embeddings_service.embed_query(current.content[:500])
        )

        best_match = None
        best_score = 0

        for old in old_knowledge:
            if old.embedding:
                old_vec = self._get_vector(old.embedding)
                similarity = self._cosine_similarity(current_vec, old_vec)

                if similarity > best_score and similarity > 0.7:
                    best_score = similarity
                    best_match = old

        if best_match:
            days_ago = (datetime.now() - best_match.created_at).days
            return f"📌 发现联系：你在 {days_ago} 天前记录的「{best_match.title}」，与当前内容高度相关。"

        return None

    def _get_vector(self, embedding) -> np.ndarray:
        """获取向量数组"""

        if embedding is None:
            return np.zeros(1024)

        if hasattr(embedding, "tolist"):
            return np.array(embedding.tolist())
        elif isinstance(embedding, list):
            return np.array(embedding)
        else:
            return np.array(embedding)

    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
            return 0.0

        dot = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        return dot / (norm1 * norm2)
