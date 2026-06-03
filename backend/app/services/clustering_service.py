"""
知识聚类服务

使用 KMeans 算法对知识向量进行聚类，自动发现主题分组
"""

import logging
from typing import List, Dict, Any, Tuple, Optional, cast
from datetime import datetime
from collections import defaultdict
import uuid

import numpy as np
from sklearn.cluster import KMeans, DBSCAN
from sklearn.metrics import silhouette_score
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Knowledge, Cluster
from app.core.vector.embeddings import embeddings_service

logger = logging.getLogger(__name__)

# scikit-learn accepts int | "auto" at runtime; type stubs only declare str.
KMEANS_N_INIT: Any = 10


def _embedding_to_list(embedding: Any) -> List[float]:
    """Convert pgvector / list embedding to a plain float list."""
    if embedding is None:
        return []
    tolist = getattr(embedding, "tolist", None)
    if callable(tolist):
        return cast(List[float], tolist())
    if isinstance(embedding, list):
        return list(embedding)
    return list(embedding)


class ClusteringService:
    """知识聚类服务"""

    def __init__(self, db_session: AsyncSession, tenant_id):
        import uuid as _uuid
        from app.services.tenant_scope import tenant_knowledge_filter

        self.db = db_session
        self.tenant_id = tenant_id
        self._tk = tenant_knowledge_filter(
            tenant_id if isinstance(tenant_id, _uuid.UUID) else _uuid.UUID(str(tenant_id))
        )

    async def get_embeddings_for_clustering(
        self, limit: int = 1000, min_embedding_exists: bool = True
    ) -> Tuple[List[Knowledge], np.ndarray]:
        """
        获取用于聚类的知识向量

        Returns:
            (knowledge_list, embeddings_matrix)
        """
        # 查询有向量的知识
        stmt = (
            select(Knowledge)
            .where(self._tk, Knowledge.embedding.is_not(None))
            .order_by(Knowledge.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        knowledge_list = list(result.scalars().all())

        if not knowledge_list:
            return [], np.array([])

        # 提取向量矩阵
        embeddings = []
        for k in knowledge_list:
            embeddings.append(_embedding_to_list(k.embedding))

        return knowledge_list, np.array(embeddings)

    async def cluster_kmeans(
        self,
        n_clusters: Optional[int] = None,
        max_clusters: int = 10,
        min_samples_per_cluster: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        使用 KMeans 进行聚类

        Args:
            n_clusters: 聚类数量（自动确定如果为 None）
            max_clusters: 最大聚类数
            min_samples_per_cluster: 每个聚类最小样本数

        Returns:
            聚类结果列表
        """
        knowledge_list, embeddings = await self.get_embeddings_for_clustering()

        if len(knowledge_list) < min_samples_per_cluster:
            logger.info(f"Not enough knowledge for clustering: {len(knowledge_list)}")
            return []

        # 自动确定最佳聚类数
        if n_clusters is None:
            n_clusters = self._find_optimal_clusters(
                embeddings, max_clusters=min(max_clusters, len(knowledge_list) // 2)
            )

        if n_clusters < 2:
            logger.info(f"Optimal clusters < 2, skipping: {n_clusters}")
            return []

        # 执行 KMeans 聚类
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=KMEANS_N_INIT)
        labels = kmeans.fit_predict(embeddings)

        # 按聚类分组
        clusters = defaultdict(list)
        for i, label in enumerate(labels):
            clusters[int(label)].append(knowledge_list[i])

        # 过滤样本数不足的聚类
        filtered_clusters = {
            label: items
            for label, items in clusters.items()
            if len(items) >= min_samples_per_cluster
        }

        # 生成聚类结果
        results = []
        for label, items in filtered_clusters.items():
            cluster_result = await self._create_cluster_record(
                label=label,
                items=items,
                center=(
                    kmeans.cluster_centers_[label]
                    if label < len(kmeans.cluster_centers_)
                    else None
                ),
                method="kmeans",
            )
            results.append(cluster_result)

        logger.info(
            f"KMeans clustering completed: {len(results)} clusters from {len(knowledge_list)} items"
        )
        return results

    async def cluster_dbscan(
        self, eps: float = 0.5, min_samples: int = 3
    ) -> List[Dict[str, Any]]:
        """
        使用 DBSCAN 进行聚类（适合发现任意形状的聚类）

        Args:
            eps: 邻域半径
            min_samples: 核心点最小样本数
        """
        knowledge_list, embeddings = await self.get_embeddings_for_clustering()

        if len(knowledge_list) < min_samples:
            return []

        # DBSCAN 聚类
        dbscan = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine")
        labels = dbscan.fit_predict(embeddings)

        # 按聚类分组（-1 表示噪声点）
        clusters = defaultdict(list)
        noise_items = []

        for i, label in enumerate(labels):
            if label == -1:
                noise_items.append(knowledge_list[i])
            else:
                clusters[int(label)].append(knowledge_list[i])

        # 生成聚类结果
        results = []
        for label, items in clusters.items():
            cluster_result = await self._create_cluster_record(
                label=label,
                items=items,
                method="dbscan",
                metadata={"eps": eps, "min_samples": min_samples},
            )
            results.append(cluster_result)

        logger.info(
            f"DBSCAN clustering completed: {len(results)} clusters, {len(noise_items)} noise items"
        )
        return results

    def _find_optimal_clusters(
        self, embeddings: np.ndarray, max_clusters: int = 10
    ) -> int:
        """
        使用肘部法则和轮廓系数确定最佳聚类数
        """
        if len(embeddings) < 3:
            return 1

        inertias = []
        silhouette_scores = []

        for k in range(2, min(max_clusters + 1, len(embeddings))):
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=KMEANS_N_INIT)
            labels = kmeans.fit_predict(embeddings)
            inertias.append(kmeans.inertia_)

            if len(set(labels)) > 1:
                score = silhouette_score(embeddings, labels)
                silhouette_scores.append(score)
            else:
                silhouette_scores.append(-1)

        if not silhouette_scores:
            return 2

        # 选择轮廓系数最高的 k
        best_idx = silhouette_scores.index(max(silhouette_scores))
        return best_idx + 2

    async def _create_cluster_record(
        self,
        label: int,
        items: List[Knowledge],
        center: Optional[np.ndarray] = None,
        method: str = "kmeans",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        创建聚类记录并存储到数据库
        """
        # 生成聚类名称（基于共同主题）
        cluster_name = await self._generate_cluster_name(items)

        # 提取关键词
        keywords = await self._extract_keywords(items)

        # 生成聚类描述
        description = await self._generate_cluster_description(items, cluster_name)

        # 计算中心向量
        if center is None:
            vectors = [
                _embedding_to_list(k.embedding)
                for k in items
                if k.embedding is not None
            ]
            if vectors:
                center = np.mean(np.asarray(vectors, dtype=float), axis=0)

        # 存储到数据库
        cluster = Cluster(
            id=uuid.uuid4(),
            name=cluster_name,
            description=description,
            keywords=keywords,
            center_embedding=center.tolist() if center is not None else None,
            knowledge_ids=[k.id for k in items],
        )

        self.db.add(cluster)
        await self.db.commit()

        return {
            "id": str(cluster.id),
            "name": cluster_name,
            "description": description,
            "keywords": keywords,
            "knowledge_count": len(items),
            "knowledge_ids": [str(k.id) for k in items],
            "method": method,
        }

    async def _generate_cluster_name(self, items: List[Knowledge]) -> str:
        """使用 LLM 生成聚类名称"""
        if not items:
            return "未命名主题"

        # 取前5条内容的标题或前100字
        titles = [item.title for item in items[:5] if item.title]
        if not titles:
            contents = [item.content[:100] for item in items[:5]]
            titles = [c[:30] + "..." for c in contents]

        from app.core.agent.llm import get_llm, Message, MessageRole

        llm = get_llm()
        prompt = f"""根据以下知识条目的标题，总结一个共同的主题名称（2-6个字）：

{chr(10).join(f'- {t}' for t in titles)}

主题名称："""

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await llm.invoke(messages)
            name = response.content.strip()
            # 限制长度
            if len(name) > 20:
                name = name[:20]
            return name
        except Exception as e:
            logger.warning(f"Failed to generate cluster name: {e}")
            return "知识主题"

    async def _extract_keywords(self, items: List[Knowledge]) -> List[str]:
        """提取聚类关键词"""
        # 合并所有内容
        all_content = " ".join([item.content[:300] for item in items[:10]])

        from app.core.agent.llm import get_llm, Message, MessageRole

        llm = get_llm()
        prompt = f"""从以下文本中提取 3-5 个最相关的关键词（用逗号分隔）：

{all_content[:800]}

关键词："""

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await llm.invoke(messages)
            keywords = [k.strip() for k in response.content.split(",") if k.strip()]
            return keywords[:5]
        except Exception as e:
            logger.warning(f"Failed to extract keywords: {e}")
            return ["知识"]

    async def _generate_cluster_description(
        self, items: List[Knowledge], name: str
    ) -> str:
        """生成聚类描述"""
        titles = [item.title for item in items[:5] if item.title]

        from app.core.agent.llm import get_llm, Message, MessageRole

        llm = get_llm()
        prompt = f"""主题：{name}
相关笔记标题：
{chr(10).join(f'- {t}' for t in titles)}

请用一句话描述这个主题的核心内容："""

        try:
            messages = [Message(role=MessageRole.USER, content=prompt)]
            response = await llm.invoke(messages)
            return response.content.strip()
        except Exception as e:
            logger.warning(f"Failed to generate description: {e}")
            return f"包含 {len(items)} 条相关知识的主题"
