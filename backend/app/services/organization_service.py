"""
知识组织服务

整合聚类、标签、摘要、去重等功能
提供一键整理和定期整理的能力
"""

import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.clustering_service import ClusteringService
from app.services.tagging_service import TaggingService
from app.services.summary_service import SummaryService
from app.services.deduplication_service import DeduplicationService
from app.models.knowledge import Knowledge
from app.services.tenant_scope import tenant_knowledge_filter
from app.models.schemas import KnowledgeUpdate

logger = logging.getLogger(__name__)


class OrganizationService:
    """知识组织服务"""

    def __init__(self, db_session: AsyncSession, tenant_id: uuid.UUID):
        self.db = db_session
        self.tenant_id = tenant_id
        self._tk = tenant_knowledge_filter(tenant_id)
        self.clustering = ClusteringService(db_session, tenant_id)
        self.tagging = TaggingService(db_session, tenant_id)
        self.summary = SummaryService()
        self.dedup = DeduplicationService(db_session, tenant_id)

    async def organize_untagged(self, limit: int = 50) -> dict:
        """
        为未打标签的知识自动生成标签
        """
        from sqlalchemy import select

        stmt = (
            select(Knowledge).where(self._tk, Knowledge.tags.is_(None)).limit(limit)
        )

        result = await self.db.execute(stmt)
        untagged = result.scalars().all()

        tagged_count = 0
        for knowledge in untagged:
            tags = await self.tagging.generate_tags(
                knowledge.content, knowledge.title, max_tags=5
            )

            if tags:
                knowledge.tags = tags
                tagged_count += 1

        await self.db.commit()

        return {
            "processed": len(untagged),
            "tagged": tagged_count,
            "timestamp": datetime.now().isoformat(),
        }

    async def organize_clusters(self) -> dict:
        """
        执行知识聚类
        """
        clusters = await self.clustering.cluster_kmeans()

        return {
            "clusters_created": len(clusters),
            "clusters": clusters,
            "timestamp": datetime.now().isoformat(),
        }

    async def generate_summaries(self, limit: int = 100) -> dict:
        """
        为长文本生成摘要
        """
        from sqlalchemy import select

        # 查找没有摘要且内容较长的知识
        stmt = (
            select(Knowledge)
            .where(self._tk, Knowledge.extra_metadata.is_(None))
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        items = result.scalars().all()

        summarized = 0
        for knowledge in items:
            if len(knowledge.content) > 500:
                summary = await self.summary.summarize(
                    knowledge.content, max_length=200, title=knowledge.title
                )

                if knowledge.extra_metadata is None:
                    knowledge.extra_metadata = {}
                knowledge.extra_metadata["auto_summary"] = summary
                summarized += 1

        await self.db.commit()

        return {
            "processed": len(items),
            "summarized": summarized,
            "timestamp": datetime.now().isoformat(),
        }

    async def cleanup_duplicates(self, dry_run: bool = True) -> dict:
        """
        清理重复内容
        """
        result = await self.dedup.remove_duplicates(keep_oldest=True, dry_run=dry_run)

        return result

    async def full_organization(self, dry_run: bool = False) -> dict:
        """
        执行完整的知识整理流程
        """
        start_time = datetime.now()

        report = {"started_at": start_time.isoformat(), "dry_run": dry_run, "steps": {}}

        # 1. 自动标签
        logger.info("Step 1: Auto-tagging...")
        tag_result = await self.organize_untagged()
        report["steps"]["tagging"] = tag_result

        # 2. 生成摘要
        logger.info("Step 2: Generating summaries...")
        summary_result = await self.generate_summaries()
        report["steps"]["summaries"] = summary_result

        # 3. 聚类
        logger.info("Step 3: Clustering...")
        cluster_result = await self.organize_clusters()
        report["steps"]["clustering"] = cluster_result

        # 4. 去重
        logger.info("Step 4: Deduplication...")
        dedup_result = await self.cleanup_duplicates(dry_run=dry_run)
        report["steps"]["deduplication"] = dedup_result

        report["finished_at"] = datetime.now().isoformat()
        report["duration_seconds"] = (datetime.now() - start_time).total_seconds()

        logger.info(f"Full organization completed in {report['duration_seconds']:.2f}s")

        return report

    async def generate_report(self) -> dict:
        """
        生成知识库整理报告
        """
        from sqlalchemy import select, func

        # 统计信息
        total_stmt = select(func.count()).select_from(Knowledge)
        total = await self.db.execute(total_stmt)

        tagged_stmt = (
            select(func.count())
            .select_from(Knowledge)
            .where(
                Knowledge.tags.is_not(None), func.array_length(Knowledge.tags, 1) > 0
            )
        )
        tagged = await self.db.execute(tagged_stmt)

        with_summary_stmt = (
            select(func.count())
            .select_from(Knowledge)
            .where(
                Knowledge.extra_metadata.is_not(None),
                Knowledge.extra_metadata["auto_summary"].is_not(None),
            )
        )
        with_summary = await self.db.execute(with_summary_stmt)

        # 标签统计
        tag_stats = await self.tagging.get_tag_stats(limit=10)

        # 聚类统计
        from app.models.knowledge import Cluster

        cluster_stmt = select(func.count()).select_from(Cluster)
        cluster_count = await self.db.execute(cluster_stmt)

        total_count = total.scalar() or 0
        tagged_count = tagged.scalar() or 0
        with_summary_count = with_summary.scalar() or 0
        cluster_total = cluster_count.scalar() or 0

        return {
            "total_knowledge": total_count,
            "tagged_count": tagged_count,
            "tag_coverage": round(
                tagged_count / (total_count or 1) * 100, 1
            ),
            "with_summary_count": with_summary_count,
            "cluster_count": cluster_total,
            "top_tags": tag_stats,
            "generated_at": datetime.now().isoformat(),
        }
