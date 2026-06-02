"""
自动标签生成服务

支持多种标签生成策略：
- LLM 关键词提取
- TF-IDF 关键词提取
- 规则匹配
"""

import re
import logging
from typing import List, Set, Optional
from collections import Counter
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.knowledge import Knowledge

logger = logging.getLogger(__name__)


class TaggingService:
    """自动标签生成服务"""

    # 预定义的停用词
    STOP_WORDS = {
        "的",
        "了",
        "是",
        "在",
        "我",
        "有",
        "和",
        "就",
        "不",
        "人",
        "都",
        "一",
        "一个",
        "上",
        "也",
        "很",
        "到",
        "说",
        "要",
        "去",
        "你",
        "会",
        "the",
        "a",
        "an",
        "is",
        "to",
        "of",
        "and",
        "in",
        "that",
        "it",
    }

    # 常见知识领域关键词
    DOMAIN_KEYWORDS = {
        "AI": ["人工智能", "机器学习", "深度学习", "神经网络", "LLM", "大模型"],
        "编程": ["Python", "JavaScript", "算法", "数据结构", "代码", "编程"],
        "产品": ["产品经理", "需求分析", "用户体验", "MVP", "敏捷"],
        "管理": ["项目管理", "团队管理", "OKR", "KPI", "领导力"],
    }

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def generate_tags(
        self, content: str, title: str = "", max_tags: int = 5, method: str = "llm"
    ) -> List[str]:
        """
        为内容生成标签

        Args:
            content: 内容文本
            title: 标题（可选）
            max_tags: 最大标签数
            method: 生成方法（llm, tfidf, hybrid）

        Returns:
            标签列表
        """
        if method == "llm":
            tags = await self._generate_tags_llm(content, title, max_tags)
        elif method == "tfidf":
            tags = self._generate_tags_tfidf(content, max_tags)
        else:  # hybrid
            tags = await self._generate_tags_hybrid(content, title, max_tags)

        # 去重并限制数量
        tags = list(dict.fromkeys(tags))[:max_tags]

        # 更新标签统计
        await self._update_tag_stats(tags)

        return tags

    async def _generate_tags_llm(
        self, content: str, title: str, max_tags: int
    ) -> List[str]:
        """使用 LLM 生成标签"""
        from app.core.agent.llm import get_llm, Message, MessageRole

        llm = get_llm()

        prompt = f"""请从以下文本中提取 {max_tags} 个最相关的关键词作为标签。

标题: {title if title else "无"}

文本内容:
{content[:800]}

要求：
1. 每个标签2-6个字
2. 用逗号分隔
3. 不要重复

标签："""

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await llm.invoke(messages)

            # 解析响应
            tags = [tag.strip() for tag in response.content.split(",") if tag.strip()]

            # 清理和过滤
            clean_tags = []
            for tag in tags:
                tag = re.sub(r"[^\w\u4e00-\u9fff]", "", tag)
                if len(tag) >= 2 and tag not in self.STOP_WORDS:
                    clean_tags.append(tag)

            return clean_tags[:max_tags]

        except Exception as e:
            logger.warning(f"LLM tag generation failed: {e}")
            return self._generate_tags_tfidf(content, max_tags)

    def _generate_tags_tfidf(self, content: str, max_tags: int) -> List[str]:
        """基于 TF-IDF 的关键词提取（简化版）"""
        # 简单的词频统计
        words = re.findall(r"[\w\u4e00-\u9fff]+", content)

        # 过滤停用词和短词
        filtered_words = [w for w in words if w not in self.STOP_WORDS and len(w) >= 2]

        # 统计词频
        word_counts = Counter(filtered_words)

        # 取频率最高的词
        tags = [word for word, _ in word_counts.most_common(max_tags)]

        return tags

    async def _generate_tags_hybrid(
        self, content: str, title: str, max_tags: int
    ) -> List[str]:
        """混合策略：LLM + 规则 + 领域匹配"""
        tags = set()

        # 1. LLM 标签
        llm_tags = await self._generate_tags_llm(content, title, max_tags)
        tags.update(llm_tags)

        # 2. 领域关键词匹配
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            for keyword in keywords:
                if (
                    keyword.lower() in content.lower()
                    or keyword.lower() in title.lower()
                ):
                    tags.add(domain)
                    break

        # 3. 如果标签不足，补充 TF-IDF 标签
        if len(tags) < max_tags:
            tfidf_tags = self._generate_tags_tfidf(content, max_tags * 2)
            for tag in tfidf_tags:
                tags.add(tag)
                if len(tags) >= max_tags:
                    break

        return list(tags)[:max_tags]

    async def _update_tag_stats(self, tags: List[str]):
        """更新标签统计（使用聚合查询替代单独的统计表）"""
        # 标签统计通过实时查询实现，不需要单独存储
        # 这样可以简化架构，避免维护 tag_stats 表
        logger.debug(f"Tags generated: {tags}")

    async def get_tag_stats(self, limit: int = 50) -> List[dict]:
        """
        获取标签使用统计

        直接从 knowledge 表聚合查询
        """
        # 使用 PostgreSQL 的 unnest 函数展开数组
        stmt = (
            select(
                func.unnest(Knowledge.tags).label("tag"), func.count().label("count")
            )
            .where(
                Knowledge.tags.is_not(None), func.array_length(Knowledge.tags, 1) > 0
            )
            .group_by("tag")
            .order_by(func.count().desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)

        return [{"tag": row[0], "count": row[1]} for row in result.all()]

    async def suggest_tags_for_untagged(self, limit: int = 50) -> List[dict]:
        """
        为未打标签的知识建议标签
        """
        # 查询没有标签的知识
        stmt = select(Knowledge).where(Knowledge.tags.is_(None)).limit(limit)

        result = await self.db.execute(stmt)
        untagged = result.scalars().all()

        suggestions = []
        for knowledge in untagged:
            tags = await self.generate_tags(
                knowledge.content, knowledge.title, max_tags=3
            )
            suggestions.append(
                {
                    "id": str(knowledge.id),
                    "title": knowledge.title,
                    "suggested_tags": tags,
                }
            )

        return suggestions
