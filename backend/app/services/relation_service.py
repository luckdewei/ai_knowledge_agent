"""
知识关系发现服务

发现知识条目之间的各种隐含关系：
- 语义相似关系
- 实体共现关系
- 时间序列关系
- 主题演化关系
"""

import logging
import re
from typing import List, Dict, Any, Tuple, Set, Optional
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

import numpy as np
import networkx as nx
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Knowledge
from app.core.vector.embeddings import embeddings_service

logger = logging.getLogger(__name__)


class RelationType(str, Enum):
    """关系类型"""

    SEMANTIC = "semantic"  # 语义相似
    CO_OCCURRENCE = "co_occurrence"  # 实体共现
    TEMPORAL = "temporal"  # 时间邻近
    TAG_SHARED = "tag_shared"  # 共享标签
    CLUSTER_SHARED = "cluster_shared"  # 共享聚类
    CAUSAL = "causal"  # 因果关系


@dataclass
class Relation:
    """关系记录"""

    source_id: str
    target_id: str
    relation_type: RelationType
    strength: float  # 0-1 之间
    evidence: str  # 关系证据描述
    discovered_at: datetime


class RelationDiscoveryService:
    """关系发现服务"""

    def __init__(self, db_session: AsyncSession, tenant_id):
        import uuid as _uuid

        self.db = db_session
        self.tenant_id = tenant_id if isinstance(tenant_id, _uuid.UUID) else _uuid.UUID(str(tenant_id))
        from app.services.tenant_scope import tenant_knowledge_filter

        self._tk = tenant_knowledge_filter(self.tenant_id)
        self.graph = nx.Graph()

    async def discover_all_relations(
        self, knowledge_ids: Optional[List[str]] = None, min_strength: float = 0.6
    ) -> List[Relation]:
        """
        发现所有类型的关系

        Args:
            knowledge_ids: 限定的知识 ID 列表（None 表示全部）
            min_strength: 最小关系强度阈值

        Returns:
            发现的关系列表
        """
        all_relations = []

        # 1. 语义相似关系
        semantic_rels = await self.discover_semantic_relations(
            knowledge_ids, min_strength
        )
        all_relations.extend(semantic_rels)

        # 2. 共享标签关系
        tag_rels = await self.discover_tag_relations(knowledge_ids)
        all_relations.extend(tag_rels)

        # 3. 时间邻近关系
        temporal_rels = await self.discover_temporal_relations(knowledge_ids)
        all_relations.extend(temporal_rels)

        # 4. 实体共现关系
        entity_rels = await self.discover_entity_relations(knowledge_ids)
        entity_rels = [r for r in entity_rels if r.strength >= min_strength]
        all_relations.extend(entity_rels)

        # 5. 因果关系（使用 LLM 分析）
        causal_rels = await self.discover_causal_relations(knowledge_ids)
        all_relations.extend(causal_rels)

        # 构建关系图谱
        self._build_graph(all_relations)

        logger.info(f"Discovered {len(all_relations)} relations")
        return all_relations

    async def discover_semantic_relations(
        self, knowledge_ids: Optional[List[str]] = None, min_similarity: float = 0.7
    ) -> List[Relation]:
        """
        发现语义相似关系

        基于向量相似度发现语义相近的知识条目
        """
        # 获取知识列表
        stmt = select(Knowledge).where(self._tk, Knowledge.embedding.is_not(None))
        if knowledge_ids:
            stmt = stmt.where(Knowledge.id.in_(knowledge_ids))

        result = await self.db.execute(stmt)
        knowledge_list = list(result.scalars().all())

        if len(knowledge_list) < 2:
            return []

        relations = []

        # 两两比较相似度（优化：只比较部分，避免 O(n^2)）
        for i in range(min(len(knowledge_list), 100)):
            k1 = knowledge_list[i]
            vec1 = self._get_vector(k1.embedding)

            for j in range(i + 1, min(len(knowledge_list), 100)):
                k2 = knowledge_list[j]
                vec2 = self._get_vector(k2.embedding)

                similarity = self._cosine_similarity(vec1, vec2)

                if similarity >= min_similarity:
                    relations.append(
                        Relation(
                            source_id=str(k1.id),
                            target_id=str(k2.id),
                            relation_type=RelationType.SEMANTIC,
                            strength=similarity,
                            evidence=f"语义相似度 {similarity:.2%}",
                            discovered_at=datetime.now(),
                        )
                    )

        logger.info(f"Discovered {len(relations)} semantic relations")
        return relations

    async def discover_tag_relations(
        self, knowledge_ids: Optional[List[str]] = None
    ) -> List[Relation]:
        """
        发现共享标签关系

        拥有相同标签的知识条目之间存在关联
        """
        from sqlalchemy import func

        # 查询有标签的知识
        stmt = select(Knowledge).where(
            self._tk,
            Knowledge.tags.is_not(None),
            func.array_length(Knowledge.tags, 1) > 0,
        )
        if knowledge_ids:
            stmt = stmt.where(Knowledge.id.in_(knowledge_ids))

        result = await self.db.execute(stmt)
        knowledge_list = list(result.scalars().all())

        # 按标签分组
        tag_to_knowledge = defaultdict(list)
        for k in knowledge_list:
            for tag in k.tags or []:
                tag_to_knowledge[tag].append(k)

        relations = []
        for tag, items in tag_to_knowledge.items():
            if len(items) < 2:
                continue

            # 同一标签下的知识两两关联
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    relations.append(
                        Relation(
                            source_id=str(items[i].id),
                            target_id=str(items[j].id),
                            relation_type=RelationType.TAG_SHARED,
                            strength=0.8,  # 固定强度
                            evidence=f"共享标签「{tag}」",
                            discovered_at=datetime.now(),
                        )
                    )

        logger.info(f"Discovered {len(relations)} tag-based relations")
        return relations

    async def discover_temporal_relations(
        self, knowledge_ids: Optional[List[str]] = None, max_days_gap: int = 7
    ) -> List[Relation]:
        """
        发现时间邻近关系

        在时间上相近的知识条目可能存在关联
        """
        stmt = select(Knowledge).where(self._tk).order_by(Knowledge.created_at)
        if knowledge_ids:
            stmt = stmt.where(Knowledge.id.in_(knowledge_ids))

        result = await self.db.execute(stmt)
        knowledge_list = list(result.scalars().all())

        if len(knowledge_list) < 2:
            return []

        relations = []

        for i in range(len(knowledge_list) - 1):
            k1 = knowledge_list[i]
            k2 = knowledge_list[i + 1]

            days_diff = (k2.created_at - k1.created_at).days

            if days_diff <= max_days_gap:
                # 时间越近，强度越高
                strength = 1.0 - (days_diff / max_days_gap)

                relations.append(
                    Relation(
                        source_id=str(k1.id),
                        target_id=str(k2.id),
                        relation_type=RelationType.TEMPORAL,
                        strength=strength,
                        evidence=f"时间相近，相隔 {days_diff} 天",
                        discovered_at=datetime.now(),
                    )
                )

        logger.info(f"Discovered {len(relations)} temporal relations")
        return relations

    async def discover_entity_relations(
        self, knowledge_ids: Optional[List[str]] = None, min_cooccurrence: int = 2
    ) -> List[Relation]:
        """
        发现实体共现关系

        提取命名实体，发现共同出现的实体
        """
        # 获取知识列表
        stmt = select(Knowledge).where(self._tk)
        if knowledge_ids:
            stmt = stmt.where(Knowledge.id.in_(knowledge_ids))

        result = await self.db.execute(stmt)
        knowledge_list = list(result.scalars().all())

        if len(knowledge_list) < 2:
            return []

        # 提取每个知识的实体
        entity_map = {}  # knowledge_id -> set of entities

        for k in knowledge_list:
            entities = await self._extract_entities(k.content)
            entity_map[str(k.id)] = entities

        # 发现共现实体
        relations = []
        knowledge_ids_list = list(entity_map.keys())

        for i in range(len(knowledge_ids_list)):
            kid1 = knowledge_ids_list[i]
            entities1 = entity_map[kid1]

            for j in range(i + 1, len(knowledge_ids_list)):
                kid2 = knowledge_ids_list[j]
                entities2 = entity_map[kid2]

                common = entities1 & entities2
                if len(common) >= min_cooccurrence:
                    strength = min(1.0, len(common) / 3.0)
                    relations.append(
                        Relation(
                            source_id=kid1,
                            target_id=kid2,
                            relation_type=RelationType.CO_OCCURRENCE,
                            strength=strength,
                            evidence=f"共同实体: {', '.join(list(common)[:3])}",
                            discovered_at=datetime.now(),
                        )
                    )

        logger.info(f"Discovered {len(relations)} entity co-occurrence relations")
        return relations

    async def discover_causal_relations(
        self, knowledge_ids: Optional[List[str]] = None
    ) -> List[Relation]:
        """
        发现因果关系

        使用 LLM 分析知识之间的因果联系
        """
        from app.core.agent.llm import get_llm, Message, MessageRole

        # 获取知识列表
        stmt = select(Knowledge).where(self._tk).limit(20)
        if knowledge_ids:
            stmt = stmt.where(Knowledge.id.in_(knowledge_ids))

        result = await self.db.execute(stmt)
        knowledge_list = list(result.scalars().all())

        if len(knowledge_list) < 2:
            return []

        relations = []
        llm = get_llm()

        # 两两分析因果关系
        for i in range(min(len(knowledge_list), 10)):
            k1 = knowledge_list[i]

            for j in range(i + 1, min(len(knowledge_list), 10)):
                k2 = knowledge_list[j]

                prompt = f"""分析以下两段知识之间是否存在因果关系。

知识A: {k1.title} - {k1.content[:200]}
知识B: {k2.title} - {k2.content[:200]}

判断：
1. A 是否导致 B？
2. B 是否导致 A？
3. 是否有因果联系？

输出JSON格式：
{{"has_causal": true/false, "direction": "A_to_B|B_to_A|bidirectional", "strength": 0.0-1.0, "reasoning": "..."}}
"""

                try:
                    messages = [Message(role=MessageRole.USER, content=prompt)]
                    response = await llm.invoke(messages)

                    import json

                    content = response.content.strip()
                    if "```json" in content:
                        start = content.find("```json") + 7
                        end = content.find("```", start)
                        content = content[start:end]

                    result = json.loads(content)

                    if result.get("has_causal"):
                        if result.get("direction") in ["A_to_B", "bidirectional"]:
                            relations.append(
                                Relation(
                                    source_id=str(k1.id),
                                    target_id=str(k2.id),
                                    relation_type=RelationType.CAUSAL,
                                    strength=result.get("strength", 0.5),
                                    evidence=result.get("reasoning", "因果关系"),
                                    discovered_at=datetime.now(),
                                )
                            )

                        if result.get("direction") in ["B_to_A", "bidirectional"]:
                            relations.append(
                                Relation(
                                    source_id=str(k2.id),
                                    target_id=str(k1.id),
                                    relation_type=RelationType.CAUSAL,
                                    strength=result.get("strength", 0.5),
                                    evidence=result.get("reasoning", "因果关系"),
                                    discovered_at=datetime.now(),
                                )
                            )
                except Exception as e:
                    logger.debug(f"Causal analysis failed: {e}")

        return relations

    async def _extract_entities(self, text: str) -> Set[str]:
        """
        提取文本中的命名实体（简化版）

        实际可使用 spaCy、LAC 等 NLP 工具
        """
        entities = set()

        # 简单的模式匹配
        # 匹配中文人名（2-4个中文字符）
        chinese_names = re.findall(r"[\u4e00-\u9fff]{2,4}", text)
        entities.update(chinese_names[:5])

        # 匹配英文单词（首字母大写）
        english_entities = re.findall(r"\b[A-Z][a-z]+\b", text)
        entities.update(english_entities[:5])

        return entities

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

    def _build_graph(self, relations: List[Relation]):
        """构建关系图谱"""
        self.graph = nx.Graph()

        for rel in relations:
            self.graph.add_edge(
                rel.source_id,
                rel.target_id,
                type=rel.relation_type.value,
                weight=rel.strength,
                evidence=rel.evidence,
            )

    def get_related_knowledge(
        self,
        knowledge_id: str,
        relation_types: Optional[List[RelationType]] = None,
        min_strength: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        获取与指定知识相关的其他知识

        Args:
            knowledge_id: 知识 ID
            relation_types: 关系类型过滤
            min_strength: 最小强度阈值

        Returns:
            相关知识列表
        """
        if knowledge_id not in self.graph:
            return []

        neighbors = []
        for neighbor in self.graph.neighbors(knowledge_id):
            edge_data = self.graph.get_edge_data(knowledge_id, neighbor)

            # 类型过滤
            if relation_types and edge_data["type"] not in [
                t.value for t in relation_types
            ]:
                continue

            # 强度过滤
            if edge_data["weight"] < min_strength:
                continue

            neighbors.append(
                {
                    "knowledge_id": neighbor,
                    "relation_type": edge_data["type"],
                    "strength": edge_data["weight"],
                    "evidence": edge_data.get("evidence", ""),
                }
            )

        # 按强度排序
        neighbors.sort(key=lambda x: x["strength"], reverse=True)
        return neighbors

    def get_knowledge_clusters(self, min_cluster_size: int = 3) -> List[List[str]]:
        """
        使用社区发现算法找出知识聚类
        """
        if self.graph.number_of_nodes() == 0:
            return []

        # 使用 Girvan-Newman 或 Louvain 算法
        try:
            from networkx.algorithms.community import louvain_communities

            communities = louvain_communities(self.graph, seed=42)

            # 过滤小社区
            return [
                list(community)
                for community in communities
                if len(community) >= min_cluster_size
            ]
        except ImportError:
            # 降级：使用连通分量
            components = list(nx.connected_components(self.graph))
            return [list(comp) for comp in components if len(comp) >= min_cluster_size]
