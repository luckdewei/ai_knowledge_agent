"""
趋势分析服务

分析知识库中的时间序列数据，发现：
- 关注点变化
- 主题演化
- 活跃度趋势
"""

import logging
import uuid
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Knowledge
from app.services.tenant_scope import tenant_knowledge_filter
from app.core.cache import CacheService, cache_key
from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TrendPoint:
    """趋势数据点"""

    date: str
    count: int
    tags: List[str]
    top_keywords: List[str]


@dataclass
class TopicEvolution:
    """主题演化"""

    topic: str
    timeline: List[Dict[str, Any]]  # [{date, mentions, related_notes}]


class TrendAnalysisService:
    """趋势分析服务"""

    def __init__(self, db_session: AsyncSession, tenant_id: uuid.UUID):
        self.db = db_session
        self.tenant_id = tenant_id
        self._tk = tenant_knowledge_filter(tenant_id)

    async def get_activity_trend(
        self, days: int = 90, interval: str = "week"
    ) -> List[TrendPoint]:
        """
        获取知识活跃度趋势

        Args:
            days: 分析的天数
            interval: 间隔 (day, week, month)
        """
        ck = cache_key("insights", str(self.tenant_id), "activity", str(days), interval)
        cached = await CacheService.get_json(ck)
        if cached is not None:
            return [
                TrendPoint(
                    date=p["date"],
                    count=p["count"],
                    tags=p.get("tags", []),
                    top_keywords=p.get("top_keywords", []),
                )
                for p in cached
            ]

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # 按时间间隔分组查询
        if interval == "day":
            date_format = "%Y-%m-%d"
        elif interval == "week":
            date_format = "%Y-%u"  # 年份-周数
        else:
            date_format = "%Y-%m"

        # 不用 array_agg(tags)：PostgreSQL 对可为 NULL 的数组列聚合会报
        # ArraySubscriptError: cannot accumulate arrays of different dimensionality
        stmt = (
            select(
                func.date_trunc(interval, Knowledge.created_at).label("period"),
                Knowledge.tags,
            )
            .where(
                and_(
                    self._tk,
                    Knowledge.created_at >= start_date,
                    Knowledge.created_at <= end_date,
                )
            )
            .order_by("period")
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        period_stats: dict[datetime, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "tags": []}
        )
        for period, tags in rows:
            bucket = period_stats[period]
            bucket["count"] += 1
            if tags:
                bucket["tags"].extend(tags)

        trend_points = []
        for period in sorted(period_stats.keys()):
            data = period_stats[period]
            top_tags = [tag for tag, _ in Counter(data["tags"]).most_common(5)]
            trend_points.append(
                TrendPoint(
                    date=period.strftime(date_format)
                    if interval != "week"
                    else period.strftime("%Y-%m-%d"),
                    count=data["count"],
                    tags=top_tags,
                    top_keywords=top_tags,
                )
            )

        await CacheService.set_json(
            ck,
            [
                {
                    "date": p.date,
                    "count": p.count,
                    "tags": p.tags,
                    "top_keywords": p.top_keywords,
                }
                for p in trend_points
            ],
            settings.cache_ttl_insights,
        )
        return trend_points

    async def get_tag_trend(
        self, tag: str, days: int = 90, interval: str = "week"
    ) -> List[Dict[str, Any]]:
        """
        获取特定标签的趋势
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # 查询包含特定标签的知识
        stmt = (
            select(
                func.date_trunc(interval, Knowledge.created_at).label("date"),
                func.count().label("count"),
            )
            .where(
                and_(
                    self._tk,
                    Knowledge.created_at >= start_date,
                    Knowledge.created_at <= end_date,
                    Knowledge.tags.contains([tag]),  # 包含该标签
                )
            )
            .group_by("date")
            .order_by("date")
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        return [
            {"date": row[0].strftime("%Y-%m-%d"), "count": row[1], "tag": tag}
            for row in rows
        ]

    async def analyze_attention_shift(
        self, days: int = 90, top_n: int = 10
    ) -> Dict[str, Any]:
        """
        分析关注点变化

        比较前期和后期的热门主题，找出上升和下降的趋势

        Returns:
            关注点变化分析结果
        """
        end_date = datetime.now()
        mid_date = end_date - timedelta(days=days // 2)
        start_date = end_date - timedelta(days=days)

        # 前期数据
        early_tags = await self._get_tag_distribution(start_date, mid_date)

        # 后期数据
        late_tags = await self._get_tag_distribution(mid_date, end_date)

        # 计算变化
        all_tags = set(early_tags.keys()) | set(late_tags.keys())

        changes = []
        for tag in all_tags:
            early_count = early_tags.get(tag, 0)
            late_count = late_tags.get(tag, 0)

            if early_count == 0:
                change_percent = 100 if late_count > 0 else 0
            else:
                change_percent = (late_count - early_count) / early_count * 100

            changes.append(
                {
                    "tag": tag,
                    "early_count": early_count,
                    "late_count": late_count,
                    "change_percent": round(change_percent, 1),
                    "trend": (
                        "up"
                        if change_percent > 20
                        else ("down" if change_percent < -20 else "stable")
                    ),
                }
            )

        # 排序
        rising = [c for c in changes if c["trend"] == "up"]
        rising.sort(key=lambda x: x["change_percent"], reverse=True)

        falling = [c for c in changes if c["trend"] == "down"]
        falling.sort(key=lambda x: x["change_percent"])

        return {
            "period": {
                "early": start_date.strftime("%Y-%m-%d"),
                "late": end_date.strftime("%Y-%m-%d"),
            },
            "rising_tags": rising[:top_n],
            "falling_tags": falling[:top_n],
            "insights": await self._generate_trend_insights(rising[:5], falling[:5]),
        }

    async def _get_tag_distribution(
        self, start_date: datetime, end_date: datetime
    ) -> Dict[str, int]:
        """获取时间段内的标签分布"""
        stmt = (
            select(
                func.unnest(Knowledge.tags).label("tag"), func.count().label("count")
            )
            .where(
                and_(
                    self._tk,
                    Knowledge.created_at >= start_date,
                    Knowledge.created_at <= end_date,
                    Knowledge.tags.is_not(None),
                    func.array_length(Knowledge.tags, 1) > 0,
                )
            )
            .group_by("tag")
        )

        result = await self.db.execute(stmt)

        return {row[0]: row[1] for row in result.all()}

    async def analyze_topic_evolution(
        self, topic_keywords: List[str], days: int = 180
    ) -> TopicEvolution:
        """
        分析特定主题的演化过程
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # 查询包含关键词的知识
        conditions = []
        for keyword in topic_keywords:
            conditions.append(Knowledge.content.contains(keyword))

        stmt = (
            select(
                Knowledge.created_at, Knowledge.title, Knowledge.content, Knowledge.tags
            )
            .where(and_(self._tk, Knowledge.created_at >= start_date, or_(*conditions)))
            .order_by(Knowledge.created_at)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        # 按月分组
        timeline = defaultdict(list)
        for row in rows:
            month_key = row[0].strftime("%Y-%m")
            timeline[month_key].append(
                {"title": row[1], "content_preview": row[2][:100], "tags": row[3] or []}
            )

        # 分析每个月的关键变化
        evolution_timeline = []
        for month, notes in sorted(timeline.items()):
            # 提取该月的关键实体
            all_content = " ".join([n["content_preview"] for n in notes])

            evolution_timeline.append(
                {
                    "date": month,
                    "mention_count": len(notes),
                    "key_notes": notes[:3],
                    "summary": await self._summarize_monthly_evolution(all_content),
                }
            )

        return TopicEvolution(
            topic=" → ".join(topic_keywords[:3]), timeline=evolution_timeline
        )

    async def find_anomalies(self, days: int = 90) -> List[Dict[str, Any]]:
        """
        发现异常点（知识量突然增加或减少的时间点）
        """
        trend = await self.get_activity_trend(days, interval="day")

        if len(trend) < 7:
            return []

        counts = [t.count for t in trend]
        mean = np.mean(counts)
        std = np.std(counts)

        anomalies = []
        for i, point in enumerate(trend):
            z_score = (point.count - mean) / std if std > 0 else 0

            if abs(z_score) > 2:  # 超过2个标准差
                anomalies.append(
                    {
                        "date": point.date,
                        "count": point.count,
                        "z_score": round(z_score, 2),
                        "type": "peak" if point.count > mean else "valley",
                        "tags": point.tags[:5],
                    }
                )

        return anomalies

    async def _summarize_monthly_evolution(self, content: str) -> str:
        """生成月度演化摘要"""
        if len(content) < 50:
            return "无显著变化"

        from app.core.agent.llm import get_llm, Message, MessageRole

        llm = get_llm()
        prompt = f"""请用一句话总结以下内容在这个月的主要关注点：

{content[:500]}

一句话总结："""

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await llm.invoke(messages)
            return response.content.strip()[:100]
        except Exception as e:
            logger.warning(f"Failed to summarize: {e}")
            return "主题持续讨论"

    async def _generate_trend_insights(
        self, rising: List[Dict], falling: List[Dict]
    ) -> List[str]:
        """生成趋势洞察描述"""
        insights = []

        if rising:
            rising_names = [r["tag"] for r in rising[:3]]
            insights.append(f"关注度上升的主题：{', '.join(rising_names)}")

        if falling:
            falling_names = [f["tag"] for f in falling[:3]]
            insights.append(f"关注度下降的主题：{', '.join(falling_names)}")

        return insights
