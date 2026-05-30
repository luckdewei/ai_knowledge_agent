"""
API 请求/响应的 Pydantic 模型。

与 knowledge.py 中的 SQLAlchemy ORM 模型分离：
- ORM：数据库读写
- Schema：HTTP 入参校验与出参序列化
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


# ========== Knowledge Schemas ==========
class KnowledgeBase(BaseModel):
    """知识条目的公共字段，Create / Response 共用。"""

    title: str = Field(..., max_length=500)
    content: str
    source_type: str = Field(..., pattern="^(file|url|clipboard|voice|wechat)$")
    source_uri: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None  # 对应 ORM 的 extra_metadata / DB 列 metadata


class KnowledgeCreate(KnowledgeBase):
    """POST 创建知识时的请求体。"""

    content_hash: Optional[str] = None  # 可选，服务端也可自行计算用于去重


class KnowledgeUpdate(BaseModel):
    """PATCH 部分更新；未传字段表示不修改。"""

    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeResponse(KnowledgeBase):
    """单条知识的 API 响应，含数据库生成的字段。"""

    # ORM 字段名为 extra_metadata（metadata 被 SQLAlchemy Base 占用）
    metadata: Optional[Dict[str, Any]] = Field(default=None, validation_alias="extra_metadata")

    id: uuid.UUID
    content_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_accessed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ========== Search Schemas ==========
class SearchRequest(BaseModel):
    """语义/混合检索的请求参数。"""

    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    source_type: Optional[str] = None
    tags: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    min_similarity: float = Field(default=0.5, ge=0, le=1)  # 向量相似度阈值


class SearchResult(BaseModel):
    """单条检索命中，附带相似度分数。"""

    knowledge: KnowledgeResponse
    similarity_score: float


class SearchResponse(BaseModel):
    """检索结果列表与耗时统计。"""

    results: List[SearchResult]
    total: int
    query_time_ms: float


# ========== Cluster Schemas ==========
class ClusterResponse(BaseModel):
    """聚类摘要，不含成员详情。"""

    id: uuid.UUID
    name: str
    description: Optional[str]
    keywords: List[str]
    knowledge_ids: List[uuid.UUID]
    knowledge_count: int
    created_at: datetime


class ClusterDetailResponse(ClusterResponse):
    """聚类详情，展开成员知识条目。"""

    knowledge_items: List[KnowledgeResponse]


# ========== Memory Schemas ==========
class MemoryCreate(BaseModel):
    """写入 Agent 记忆的请求体。"""

    memory_type: str = Field(..., pattern="^(short_term|long_term|episodic)$")
    content: str
    context: Optional[Dict[str, Any]] = None
    importance_score: float = 0.5
    ttl_hours: Optional[int] = None  # 短期记忆 TTL，服务端换算为 expires_at


class MemoryResponse(BaseModel):
    """单条记忆的 API 响应。"""

    id: uuid.UUID
    memory_type: str
    content: str
    context: Dict[str, Any]
    importance_score: float
    created_at: datetime
    expires_at: Optional[datetime]
