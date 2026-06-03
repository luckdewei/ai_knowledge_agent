import hashlib
import logging
import uuid
from datetime import datetime
from typing import Any, List, Optional, Tuple, cast
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import desc
from app.models.knowledge import Knowledge, Cluster
from app.models.schemas import KnowledgeCreate, KnowledgeUpdate, SearchRequest
from app.core.vector.embeddings import embeddings_service
from app.core.cache import CacheService, cache_key, invalidate_knowledge_caches
from app.core.config import settings

logger = logging.getLogger(__name__)


class KnowledgeService:
    """知识库 CRUD + 向量检索服务（按租户隔离）"""

    def __init__(self, db: AsyncSession, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """计算内容的 SHA256 哈希，用于去重"""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def create(self, knowledge_in: KnowledgeCreate) -> Knowledge:
        """创建知识条目（自动向量化）"""

        # 1. 计算内容哈希（去重检查）
        content_hash = knowledge_in.content_hash or self.compute_content_hash(
            knowledge_in.content
        )

        # 2. 检查是否已存在
        existing = await self.get_by_hash(content_hash)
        if existing:
            logger.info(f"Knowledge already exists: {content_hash[:8]}")
            return existing

        # 3. 创建知识对象
        knowledge = Knowledge(
            tenant_id=self.tenant_id,
            title=knowledge_in.title,
            content=knowledge_in.content,
            content_hash=content_hash,
            source_type=knowledge_in.source_type,
            source_uri=knowledge_in.source_uri,
            tags=knowledge_in.tags,
            extra_metadata=knowledge_in.metadata,
        )

        # 4. 向量化（异步并行）
        try:
            embedding = await embeddings_service.embed_query(
                knowledge_in.content[:2000]
            )  # 限制长度
            knowledge.embedding = cast(
                Any, embedding
            )  # pgvector 运行时接受 list[float]
            logger.debug(f"Generated embedding for {knowledge.title[:50]}")
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            # 不阻断流程，向量可为空

        # 5. 存储到数据库
        self.db.add(knowledge)
        await self.db.commit()
        await self.db.refresh(knowledge)

        logger.info(f"Created knowledge: {knowledge.id}, title={knowledge.title[:50]}")
        await invalidate_knowledge_caches(self.tenant_id)
        return knowledge

    async def create_batch(
        self, knowledge_list: List[KnowledgeCreate]
    ) -> List[Knowledge]:
        """批量创建（高效）"""

        # 1. 计算所有哈希
        for k in knowledge_list:
            if not k.content_hash:
                k.content_hash = self.compute_content_hash(k.content)

        # 2. 批量去重检查
        hashes = [k.content_hash for k in knowledge_list]
        stmt = select(Knowledge).where(
            Knowledge.tenant_id == self.tenant_id,
            Knowledge.content_hash.in_(hashes),
        )
        result = await self.db.execute(stmt)
        existing_map = {k.content_hash: k for k in result.scalars().all()}

        # 3. 过滤出新记录
        new_items = []
        for k in knowledge_list:
            if k.content_hash not in existing_map:
                new_items.append(k)

        if not new_items:
            return list(existing_map.values())

        # 4. 批量向量化
        contents = [k.content[:2000] for k in new_items]
        try:
            embeddings = await embeddings_service.embed(contents)
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            embeddings = [None] * len(new_items)

        # 5. 创建对象
        knowledge_objs = []
        for i, k in enumerate(new_items):
            knowledge = Knowledge(
                tenant_id=self.tenant_id,
                title=k.title,
                content=k.content,
                content_hash=k.content_hash,
                source_type=k.source_type,
                source_uri=k.source_uri,
                tags=k.tags,
                extra_metadata=k.metadata,
                embedding=cast(Any, embeddings[i]) if embeddings[i] else None,
            )
            self.db.add(knowledge)
            knowledge_objs.append(knowledge)

        await self.db.commit()
        for obj in knowledge_objs:
            await self.db.refresh(obj)

        logger.info(f"Batch created {len(knowledge_objs)} knowledge items")
        return knowledge_objs

    async def get_by_hash(self, content_hash: str) -> Optional[Knowledge]:
        """通过哈希获取"""
        stmt = select(Knowledge).where(
            Knowledge.tenant_id == self.tenant_id,
            Knowledge.content_hash == content_hash,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_source_uri(self, source_uri: str) -> Optional[Knowledge]:
        """按来源 URL 查找（用于网页重新抓取更新）。"""
        if not source_uri:
            return None
        stmt = (
            select(Knowledge)
            .where(
                Knowledge.tenant_id == self.tenant_id,
                Knowledge.source_uri == source_uri,
                Knowledge.source_type == "url",
            )
            .order_by(desc(Knowledge.updated_at))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def replace_from_ingestion(
        self,
        knowledge_id: str,
        *,
        title: str,
        content: str,
        content_hash: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[Knowledge]:
        """重新摄取时覆盖正文、哈希与向量。"""
        kid = uuid.UUID(knowledge_id) if isinstance(knowledge_id, str) else knowledge_id
        stmt = select(Knowledge).where(
            Knowledge.id == kid,
            Knowledge.tenant_id == self.tenant_id,
        )
        result = await self.db.execute(stmt)
        knowledge = result.scalar_one_or_none()
        if not knowledge:
            return None

        knowledge.title = title
        knowledge.content = content
        knowledge.content_hash = content_hash
        if tags is not None:
            knowledge.tags = tags
        if metadata is not None:
            knowledge.extra_metadata = metadata

        try:
            embedding = await embeddings_service.embed_query(content[:2000])
            knowledge.embedding = cast(Any, embedding)
        except Exception as e:
            logger.error(f"Re-embedding failed: {e}")

        await self.db.commit()
        await self.db.refresh(knowledge)
        await invalidate_knowledge_caches(self.tenant_id)
        logger.info(f"Refreshed knowledge from ingestion: {knowledge.id}")
        return knowledge

    async def get_by_id(self, knowledge_id: str) -> Optional[Knowledge]:
        """通过 ID 获取"""
        stmt = select(Knowledge).where(
            Knowledge.id == knowledge_id,
            Knowledge.tenant_id == self.tenant_id,
        )
        result = await self.db.execute(stmt)
        knowledge = result.scalar_one_or_none()
        if knowledge:
            knowledge.update_access_time()
            await self.db.commit()  # 把改动保存到数据库
            await self.db.refresh(knowledge)  # 再从数据库读回来，保证对象是最新状态
        return knowledge

    async def search_semantic(
        self, request: SearchRequest
    ) -> Tuple[List[Tuple[Knowledge, float]], int]:
        """
        语义向量搜索（混合检索）

        返回: (结果列表, 总数)
        """

        # 1. 获取查询向量
        query_vector = await embeddings_service.embed_query(request.query)

        # 2. 构建过滤条件
        filters = [Knowledge.tenant_id == self.tenant_id]
        if request.source_type:
            filters.append(Knowledge.source_type == request.source_type)
        if request.tags:
            filters.append(
                or_(*[Knowledge.tags.contains([tag]) for tag in request.tags])
            )
        if request.date_from:
            filters.append(Knowledge.created_at >= request.date_from)
        if request.date_to:
            filters.append(Knowledge.created_at <= request.date_to)

        # 3. 执行向量相似度搜索
        # pgvector 的 <=> 是余弦距离，1 - 余弦距离 = 余弦相似度
        stmt = select(
            Knowledge,
            (1 - Knowledge.embedding.cosine_distance(query_vector)).label("similarity"),
        ).where(Knowledge.embedding.is_not(None))

        if filters:
            stmt = stmt.where(and_(*filters))

        # 按相似度排序
        stmt = stmt.order_by(desc("similarity")).limit(request.top_k)

        result = await self.db.execute(stmt)
        rows = result.all()

        # 4. 过滤低相似度结果
        results = []
        for knowledge, similarity in rows:
            if similarity >= request.min_similarity:
                results.append((knowledge, float(similarity)))

        return results, len(results)

    async def search_keywords(self, query: str, limit: int = 10) -> List[Knowledge]:
        """关键词全文搜索（备用）"""
        # PostgreSQL 全文搜索
        stmt = (
            select(Knowledge)
            .where(
                Knowledge.tenant_id == self.tenant_id,
                func.to_tsvector("chinese", Knowledge.content).match(query),
            )
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_recent(self, days: int = 30, limit: int = 50) -> List[Knowledge]:
        """获取最近的知识条目"""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=days)

        stmt = (
            select(Knowledge)
            .where(
                Knowledge.tenant_id == self.tenant_id,
                Knowledge.created_at >= cutoff,
            )
            .order_by(desc(Knowledge.created_at))
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_time_range(
        self, start: datetime, end: datetime
    ) -> List[Knowledge]:
        """时间范围查询（用于趋势分析）"""
        stmt = (
            select(Knowledge)
            .where(
                Knowledge.tenant_id == self.tenant_id,
                Knowledge.created_at >= start,
                Knowledge.created_at <= end,
            )
            .order_by(Knowledge.created_at)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self, knowledge_id: str, update_data: KnowledgeUpdate
    ) -> Optional[Knowledge]:
        """更新知识条目"""
        knowledge = await self.get_by_id(knowledge_id)
        if not knowledge:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)

        # Schema 字段 metadata 对应 ORM 属性 extra_metadata
        field_map = {"metadata": "extra_metadata"}
        for field, value in update_dict.items():
            setattr(knowledge, field_map.get(field, field), value)

        # 如果内容更新了，重新向量化
        if "content" in update_dict and update_dict["content"]:
            try:
                embedding = await embeddings_service.embed_query(
                    knowledge.content[:2000]
                )
                knowledge.embedding = cast(Any, embedding)
            except Exception as e:
                logger.error(f"Re-embedding failed: {e}")

        await self.db.commit()
        await self.db.refresh(knowledge)
        await invalidate_knowledge_caches(self.tenant_id)

        return knowledge

    async def delete(self, knowledge_id: str) -> bool:
        """删除知识条目"""
        knowledge = await self.get_by_id(knowledge_id)
        if not knowledge:
            return False

        await self.db.delete(knowledge)
        await self.db.commit()
        await invalidate_knowledge_caches(self.tenant_id)
        return True

    async def get_stats(self) -> dict:
        """获取统计信息（Redis 缓存 60s）"""
        ck = cache_key("stats", "knowledge", str(self.tenant_id))
        cached = await CacheService.get_json(ck)
        if cached is not None:
            return cached

        # 总数
        total_stmt = (
            select(func.count())
            .select_from(Knowledge)
            .where(Knowledge.tenant_id == self.tenant_id)
        )
        total = await self.db.execute(total_stmt)

        type_stmt = (
            select(Knowledge.source_type, func.count().label("count"))
            .where(Knowledge.tenant_id == self.tenant_id)
            .group_by(Knowledge.source_type)
        )
        type_result = await self.db.execute(type_stmt)

        # 标签统计
        tag_stmt = (
            select(
                func.unnest(Knowledge.tags).label("tag"), func.count().label("count")
            )
            .where(Knowledge.tenant_id == self.tenant_id)
            .group_by("tag")
            .order_by(desc("count"))
            .limit(20)
        )
        tag_result = await self.db.execute(tag_stmt)

        stats = {
            "total_knowledge": total.scalar() or 0,
            "by_source_type": {row[0]: row[1] for row in type_result.all()},
            "top_tags": [{"tag": row[0], "count": row[1]} for row in tag_result.all()],
        }
        await CacheService.set_json(ck, stats, settings.cache_ttl_stats)
        return stats
