"""
知识去重服务

使用多种策略检测和清理重复内容：
- 精确哈希去重（SHA256）
- 向量相似度去重（余弦相似度）
- MinHash 近似去重（可选）
"""

import hashlib
import logging
from typing import List, Tuple, Set, Optional
from datetime import datetime
from collections import defaultdict

import numpy as np
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Knowledge

logger = logging.getLogger(__name__)


class DeduplicationService:
    """去重服务"""

    # 向量相似度阈值（超过此值视为重复）
    SIMILARITY_THRESHOLD = 0.95

    # MinHash 配置
    MINHASH_PERMUTATIONS = 128

    def __init__(self, db_session: AsyncSession, tenant_id):
        import uuid as _uuid
        from app.services.tenant_scope import tenant_knowledge_filter

        self.db = db_session
        self.tenant_id = tenant_id
        self._tk = tenant_knowledge_filter(
            tenant_id if isinstance(tenant_id, _uuid.UUID) else _uuid.UUID(str(tenant_id))
        )

    @staticmethod
    def compute_hash(content: str) -> str:
        """计算内容哈希"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def find_exact_duplicates(self) -> List[dict]:
        """
        查找精确重复的内容（基于 content_hash）

        Returns:
            重复组列表
        """
        # 按 content_hash 分组
        stmt = (
            select(
                Knowledge.content_hash,
                func.array_agg(Knowledge.id).label("ids"),
                func.count().label("count"),
            )
            .where(Knowledge.content_hash.is_not(None))
            .group_by(Knowledge.content_hash)
            .having(func.count() > 1)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        duplicates = []
        for row in rows:
            duplicates.append(
                {"hash": row[0], "ids": row[1], "count": row[2], "type": "exact"}
            )

        logger.info(f"Found {len(duplicates)} exact duplicate groups")
        return duplicates

    async def find_similar_duplicates(
        self, threshold: float = SIMILARITY_THRESHOLD, limit: int = 500
    ) -> List[dict]:
        """
        查找相似重复的内容（基于向量相似度）

        Args:
            threshold: 相似度阈值
            limit: 最大处理数量

        Returns:
            相似组列表
        """
        # 获取有向量的知识
        stmt = (
            select(Knowledge)
            .where(self._tk, Knowledge.embedding.is_not(None))
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        knowledge_list = list(result.scalars().all())

        if len(knowledge_list) < 2:
            return []

        similar_groups = []
        visited = set()

        for i, k1 in enumerate(knowledge_list):
            if k1.id in visited:
                continue

            group = [k1.id]
            vec1 = self._get_vector(k1.embedding)

            for j, k2 in enumerate(knowledge_list[i + 1 :], start=i + 1):
                if k2.id in visited:
                    continue

                vec2 = self._get_vector(k2.embedding)
                similarity = self._cosine_similarity(vec1, vec2)

                if similarity >= threshold:
                    group.append(k2.id)
                    visited.add(k2.id)

            if len(group) > 1:
                similar_groups.append(
                    {
                        "ids": group,
                        "count": len(group),
                        "type": "similar",
                        "similarity": threshold,
                    }
                )
                visited.add(k1.id)

        logger.info(f"Found {len(similar_groups)} similar duplicate groups")
        return similar_groups

    async def remove_duplicates(
        self, keep_oldest: bool = True, dry_run: bool = True
    ) -> dict:
        """
        清理重复内容

        Args:
            keep_oldest: 是否保留最早的（否则保留最新的）
            dry_run: 是否只预览不实际删除

        Returns:
            清理结果统计
        """
        result = {
            "exact_duplicates_found": 0,
            "similar_duplicates_found": 0,
            "items_to_remove": [],
            "items_removed": 0,
            "errors": [],
        }

        # 1. 处理精确重复
        exact_duplicates = await self.find_exact_duplicates()
        result["exact_duplicates_found"] = len(exact_duplicates)

        for group in exact_duplicates:
            removed = await self._remove_group(
                group["ids"], keep_oldest=keep_oldest, dry_run=dry_run
            )
            result["items_to_remove"].extend(removed)

        # 2. 处理相似重复
        similar_duplicates = await self.find_similar_duplicates()
        result["similar_duplicates_found"] = len(similar_duplicates)

        for group in similar_duplicates:
            removed = await self._remove_group(
                group["ids"], keep_oldest=keep_oldest, dry_run=dry_run
            )
            result["items_to_remove"].extend(removed)

        if not dry_run:
            result["items_removed"] = len(result["items_to_remove"])

        return result

    async def _remove_group(
        self, ids: List[str], keep_oldest: bool = True, dry_run: bool = True
    ) -> List[str]:
        """
        移除一个重复组，保留一条

        Returns:
            被移除的 ID 列表
        """
        if len(ids) <= 1:
            return []

        # 获取知识详情
        stmt = select(Knowledge).where(self._tk, Knowledge.id.in_(ids))
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        # 排序决定保留哪个
        items.sort(key=lambda x: x.created_at)

        if keep_oldest:
            keep_id = items[0].id
            to_remove = [item.id for item in items[1:]]
        else:
            keep_id = items[-1].id
            to_remove = [item.id for item in items[:-1]]

        if not dry_run:
            for remove_id in to_remove:
                stmt = select(Knowledge).where(self._tk, Knowledge.id == remove_id)
                result = await self.db.execute(stmt)
                to_delete = result.scalar_one_or_none()
                if to_delete:
                    await self.db.delete(to_delete)

            await self.db.commit()
            logger.info(f"Removed {len(to_remove)} duplicates, kept {keep_id}")

        return [str(item_id) for item_id in to_remove]

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
