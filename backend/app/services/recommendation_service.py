"""
知识推荐服务

基于关系图谱和用户行为推荐相关知识
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Knowledge
from app.services.relation_service import RelationDiscoveryService, RelationType

logger = logging.getLogger(__name__)


class KnowledgeRecommendationService:
    """知识推荐服务"""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.relation_service = RelationDiscoveryService(db_session)

    async def recommend_related(
        self,
        knowledge_id: str,
        limit: int = 5,
        include_types: Optional[List[RelationType]] = None,
    ) -> List[Dict[str, Any]]:
        """
        推荐与指定知识相关的其他知识

        Args:
            knowledge_id: 源知识 ID
            limit: 推荐数量
            include_types: 包含的关系类型

        Returns:
            推荐列表
        """
        # 发现关系（如果还没有）
        await self.relation_service.discover_all_relations()

        # 获取相关知识
        related = self.relation_service.get_related_knowledge(
            knowledge_id, relation_types=include_types, min_strength=0.5
        )

        # 获取知识详情
        recommendations = []
        for item in related[:limit]:
            stmt = select(Knowledge).where(Knowledge.id == item["knowledge_id"])
            result = await self.db.execute(stmt)
            knowledge = result.scalar_one_or_none()

            if knowledge:
                recommendations.append(
                    {
                        "id": str(knowledge.id),
                        "title": knowledge.title,
                        "content_preview": knowledge.content[:200],
                        "relation_type": item["relation_type"],
                        "relation_strength": item["strength"],
                        "relation_evidence": item["evidence"],
                        "created_at": knowledge.created_at.isoformat(),
                    }
                )

        return recommendations

    async def recommend_by_tags(
        self, tags: List[str], limit: int = 10, exclude_ids: Optional[List[str]] = None
    ) -> List[Knowledge]:
        """
        基于标签推荐知识
        """
        from sqlalchemy import func

        stmt = select(Knowledge).where(
            Knowledge.tags.is_not(None), Knowledge.tags.overlap(tags)  # 有重叠标签
        )

        if exclude_ids:
            stmt = stmt.where(~Knowledge.id.in_(exclude_ids))

        stmt = stmt.order_by(
            func.array_length(Knowledge.tags, 1).desc(), Knowledge.created_at.desc()
        ).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def recommend_similar_by_content(
        self, content: str, limit: int = 5, exclude_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        基于内容相似度推荐知识
        """
        from app.services.knowledge_service import KnowledgeService
        from app.models.schemas import SearchRequest

        knowledge_service = KnowledgeService(self.db)

        search_request = SearchRequest(query=content, top_k=limit, min_similarity=0.6)

        results, _ = await knowledge_service.search_semantic(search_request)

        # 过滤排除的 ID
        exclude_set = set(exclude_ids or [])
        filtered = [
            {
                "id": str(k.id),
                "title": k.title,
                "content_preview": k.content[:200],
                "similarity": score,
                "tags": k.tags or [],
            }
            for k, score in results
            if str(k.id) not in exclude_set
        ]

        return filtered[:limit]

    async def get_knowledge_network(
        self, knowledge_id: str, depth: int = 2, max_nodes: int = 20
    ) -> Dict[str, Any]:
        """
        获取知识的关系网络（用于可视化）

        Returns:
            {"nodes": [...], "edges": [...]}
        """
        await self.relation_service.discover_all_relations()

        graph = self.relation_service.graph

        # BFS 获取子图
        if knowledge_id not in graph:
            return {"nodes": [], "edges": []}

        visited = set()
        queue = [(knowledge_id, 0)]
        nodes = set([knowledge_id])

        while queue and len(nodes) < max_nodes:
            current, d = queue.pop(0)
            if d >= depth:
                continue

            for neighbor in graph.neighbors(current):
                if neighbor not in visited:
                    visited.add(neighbor)
                    nodes.add(neighbor)
                    queue.append((neighbor, d + 1))

        # 构建节点信息
        node_list = []
        for node_id in nodes:
            stmt = select(Knowledge).where(Knowledge.id == node_id)
            result = await self.db.execute(stmt)
            knowledge = result.scalar_one_or_none()

            if knowledge:
                node_list.append(
                    {"id": node_id, "title": knowledge.title[:30], "type": "knowledge"}
                )

        # 构建边信息
        edge_list = []
        for u, v, data in graph.edges(data=True):
            if u in nodes and v in nodes:
                edge_list.append(
                    {
                        "source": u,
                        "target": v,
                        "type": data.get("type", "unknown"),
                        "weight": data.get("weight", 0.5),
                    }
                )

        return {"nodes": node_list, "edges": edge_list}
