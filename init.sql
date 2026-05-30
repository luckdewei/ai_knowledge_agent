-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 创建知识表
CREATE TABLE IF NOT EXISTS knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) UNIQUE,  -- 用于去重
    source_type VARCHAR(50) NOT NULL,  -- 'file', 'url', 'clipboard', 'voice'
    source_uri TEXT,                   -- 原始来源标识
    tags TEXT[],                       -- PostgreSQL 数组类型存储标签
    embedding vector(1024),            -- 1024维向量（BGE模型）
    metadata JSONB,                    -- 灵活存储额外元数据
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_accessed_at TIMESTAMPTZ
);

-- 创建聚类结果表
CREATE TABLE IF NOT EXISTS clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    description TEXT,
    keywords TEXT[],
    center_embedding vector(1024),
    knowledge_ids UUID[],
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 创建标签统计表（可选，用于快速统计）
CREATE TABLE IF NOT EXISTS tag_stats (
    tag_name VARCHAR(100) PRIMARY KEY,
    usage_count INTEGER DEFAULT 1,
    last_used_at TIMESTAMPTZ DEFAULT NOW()
);

-- 创建记忆表（Agent 的长短期记忆）
CREATE TABLE IF NOT EXISTS agent_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_type VARCHAR(50) NOT NULL,  -- 'short_term', 'long_term', 'episodic'
    content TEXT NOT NULL,
    context JSONB,
    importance_score FLOAT DEFAULT 0.5,
    embedding vector(1024),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ  -- 短期记忆过期时间
);

-- 创建向量索引（IVFFlat 或 HNSW）
-- IVFFlat 需要先有数据再创建，这里先创建 HNSW（pgvector 0.5.0+）
CREATE INDEX IF NOT EXISTS knowledge_embedding_idx ON knowledge 
USING hnsw (embedding vector_cosine_ops);

-- 创建普通索引加速查询
CREATE INDEX IF NOT EXISTS knowledge_created_at_idx ON knowledge (created_at DESC);
CREATE INDEX IF NOT EXISTS knowledge_source_type_idx ON knowledge (source_type);
CREATE INDEX IF NOT EXISTS knowledge_tags_idx ON knowledge USING GIN (tags);
CREATE INDEX IF NOT EXISTS knowledge_content_hash_idx ON knowledge (content_hash);

-- 创建更新时间自动更新的触发器函数
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_knowledge_updated_at 
    BEFORE UPDATE ON knowledge 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();