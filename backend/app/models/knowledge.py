"""
知识库 ORM 模型。

对应 init.sql 中的 knowledge / clusters / agent_memories 三张表。
向量字段使用 pgvector（1024 维，与 BGE 嵌入模型一致）。
"""

from sqlalchemy import UUID, String, Text, DateTime, Float, Index, func
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column

# VECTOR 来自 pgvector 扩展，不在 sqlalchemy.dialects.postgresql 中
from pgvector.sqlalchemy import VECTOR, Vector
from datetime import datetime
import uuid
from typing import List, Optional, Dict, Any

from app.core.database import Base


class Knowledge(Base):
    """单条知识条目，支持全文存储与向量检索。"""

    __tablename__ = "knowledge"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )  # 内容哈希，用于入库去重
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # 'file' | 'url' | 'clipboard' | 'voice'
    source_uri: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    embedding: Mapped[Optional[Vector]] = mapped_column(
        VECTOR(1024), nullable=True
    )  # 语义向量，供 HNSW 近似最近邻检索

    # 属性名不能叫 metadata：DeclarativeBase 已占用该名作为 MetaData 注册表
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # 最后访问时间
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 复合索引
    __table_args__ = (
        Index("idx_knowledge_source_created", "source_type", "created_at"),
        Index("idx_knowledge_tags_gin", "tags", postgresql_using="gin"),
    )

    def to_dict(self) -> dict:
        """转换为字典，用于 API 响应"""
        return {
            "id": str(self.id),
            "title": self.title,
            "content": self.content,
            "content_hash": self.content_hash,
            "source_type": self.source_type,
            "source_uri": self.source_uri,
            "tags": self.tags or [],
            "metadata": self.extra_metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_accessed_at": (
                self.last_accessed_at.isoformat() if self.last_accessed_at else None
            ),
        }

    def update_access_time(self):
        """更新最后访问时间"""
        self.last_accessed_at = datetime.now()


class Cluster(Base):
    """知识聚类结果，记录主题簇及其成员。"""

    __tablename__ = "clusters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keywords: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    center_embedding: Mapped[Optional[Vector]] = mapped_column(
        VECTOR(1024), nullable=True
    )  # 簇中心向量
    knowledge_ids: Mapped[Optional[List[uuid.UUID]]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )  # 归属该簇的知识 ID 列表
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_dict(self) -> dict:
        """转换为字典，用于 API 响应"""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords or [],
            "knowledge_ids": [str(kid) for kid in (self.knowledge_ids or [])],
            "knowledge_count": len(self.knowledge_ids or []),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AgentMemory(Base):
    """Agent 长短期记忆，支持按重要度与过期时间淘汰。"""

    __tablename__ = "agent_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    memory_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'short_term', 'long_term', 'episodic'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    importance_score: Mapped[float] = mapped_column(Float, default=0.5)
    embedding: Mapped[Optional[Vector]] = mapped_column(VECTOR(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def to_dict(self) -> dict:
        """转换为字典，用于 API 响应"""
        return {
            "id": str(self.id),
            "memory_type": self.memory_type,
            "content": self.content,
            "context": self.context or {},
            "importance_score": self.importance_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
