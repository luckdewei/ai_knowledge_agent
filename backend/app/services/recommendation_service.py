"""
知识推荐服务

基于关系图谱和用户行为推荐相关知识
"""

import logging
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Knowledge
from app.services.relation_service import RelationDiscoveryService, RelationType
from app.services.tenant_scope import tenant_knowledge_filter

logger = logging.getLogger(__name__)


class KnowledgeRecommendationService:
    """知识推荐服务"""

    def __init__(self, db_session: AsyncSession, tenant_id: uuid.UUID):
        self.db = db_session
        self.tenant_id = tenant_id
        self.relation_service = RelationDiscoveryService(db_session, tenant_id)

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
        network = await self.get_knowledge_network(
            knowledge_id, depth=1, max_nodes=limit + 1
        )
        neighbor_ids = [
            e["target"]
            for e in network["edges"]
            if e["source"] == knowledge_id
        ][:limit]

        recommendations = []
        for nid in neighbor_ids:
            stmt = select(Knowledge).where(
                tenant_knowledge_filter(self.tenant_id), Knowledge.id == nid
            )
            result = await self.db.execute(stmt)
            knowledge = result.scalar_one_or_none()
            if not knowledge:
                continue
            edge = next(
                (
                    e
                    for e in network["edges"]
                    if e["source"] == knowledge_id and e["target"] == nid
                ),
                None,
            )
            recommendations.append(
                {
                    "id": str(knowledge.id),
                    "title": knowledge.title,
                    "content_preview": knowledge.content[:200],
                    "relation_type": edge["type"] if edge else "related",
                    "relation_strength": edge["weight"] if edge else 0.5,
                    "relation_evidence": "标签或语义相似",
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

        tag_match = or_(*[Knowledge.tags.contains([tag]) for tag in tags])
        stmt = select(Knowledge).where(
            tenant_knowledge_filter(self.tenant_id),
            Knowledge.tags.is_not(None),
            tag_match,
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

        knowledge_service = KnowledgeService(self.db, self.tenant_id)

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

        使用标签重叠 + 语义检索构建局部子图，避免全库 discover_all_relations 超时。
        """
        _ = depth  # 预留：后续可做多跳 BFS

        stmt = select(Knowledge).where(Knowledge.id == knowledge_id)
        result = await self.db.execute(stmt)
        center = result.scalar_one_or_none()
        if not center:
            return {"nodes": [], "edges": []}

        center_id = str(center.id)
        node_ids: list[str] = [center_id]
        edge_list: list[Dict[str, Any]] = []

        tags = center.tags or []
        if tags:
            from sqlalchemy import func

            tag_match = or_(*[Knowledge.tags.contains([tag]) for tag in tags])
            neighbor_stmt = (
                select(Knowledge)
                .where(
                    Knowledge.id != center.id,
                    Knowledge.tags.is_not(None),
                    tag_match,
                )
                .order_by(Knowledge.created_at.desc())
                .limit(max(0, max_nodes - 1))
            )
            neighbors = (await self.db.execute(neighbor_stmt)).scalars().all()
            for nb in neighbors:
                nid = str(nb.id)
                node_ids.append(nid)
                shared = set(tags) & set(nb.tags or [])
                edge_list.append(
                    {
                        "source": center_id,
                        "target": nid,
                        "type": RelationType.TAG_SHARED.value,
                        "weight": min(1.0, 0.5 + 0.1 * len(shared)),
                    }
                )

        content_snippet = (center.content or center.title or "").strip()[:500]
        if len(node_ids) < max_nodes and content_snippet:
            similar = await self.recommend_similar_by_content(
                content_snippet,
                limit=max_nodes - len(node_ids),
                exclude_ids=node_ids,
            )
            for item in similar:
                nid = item["id"]
                if nid in node_ids:
                    continue
                node_ids.append(nid)
                edge_list.append(
                    {
                        "source": center_id,
                        "target": nid,
                        "type": RelationType.SEMANTIC.value,
                        "weight": float(item.get("similarity", 0.6)),
                    }
                )
                if len(node_ids) >= max_nodes:
                    break

        node_list = []
        for node_id in node_ids:
            row = await self.db.execute(
                select(Knowledge).where(Knowledge.id == node_id)
            )
            knowledge = row.scalar_one_or_none()
            if knowledge:
                node_list.append(
                    {
                        "id": node_id,
                        "title": knowledge.title[:30],
                        "type": "knowledge",
                    }
                )

        return {"nodes": node_list, "edges": edge_list}
