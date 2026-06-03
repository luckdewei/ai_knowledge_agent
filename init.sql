-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- ========== 租户与用户 ==========
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    username VARCHAR(64) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    role VARCHAR(32) NOT NULL DEFAULT 'member',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT users_tenant_username_unique UNIQUE (tenant_id, username)
);

-- 创建知识表
CREATE TABLE IF NOT EXISTS knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64),  -- 租户内去重
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
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_tenant_content_hash_idx
    ON knowledge (tenant_id, content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS knowledge_tenant_created_idx ON knowledge (tenant_id, created_at DESC);

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

-- ========== 待办事项（Todo 工具） ==========
CREATE TABLE IF NOT EXISTS todos (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    priority INTEGER NOT NULL DEFAULT 1,
    due_date TIMESTAMPTZ,
    category VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS todos_completed_idx ON todos (completed);
CREATE INDEX IF NOT EXISTS todos_priority_due_idx ON todos (priority DESC, due_date);

CREATE TRIGGER update_todos_updated_at
    BEFORE UPDATE ON todos
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ========== 知识关系（图谱持久化） ==========
CREATE TABLE IF NOT EXISTS knowledge_relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES knowledge(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES knowledge(id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,
    strength DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    evidence TEXT,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT knowledge_relations_unique UNIQUE (source_id, target_id, relation_type)
);

CREATE INDEX IF NOT EXISTS knowledge_relations_source_idx ON knowledge_relations (source_id);
CREATE INDEX IF NOT EXISTS knowledge_relations_target_idx ON knowledge_relations (target_id);
CREATE INDEX IF NOT EXISTS knowledge_relations_type_idx ON knowledge_relations (relation_type);

-- ========== Agent 对话会话 ==========
CREATE TABLE IF NOT EXISTS agent_sessions (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    title VARCHAR(200),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(64) NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    thinking TEXT,
    tool_calls JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS chat_messages_session_idx ON chat_messages (session_id, created_at);

CREATE TRIGGER update_agent_sessions_updated_at
    BEFORE UPDATE ON agent_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_clusters_updated_at
    BEFORE UPDATE ON clusters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ========== 工具调用日志 ==========
CREATE TABLE IF NOT EXISTS tool_invocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_name VARCHAR(50) NOT NULL,
    params JSONB,
    status VARCHAR(20) NOT NULL,
    result JSONB,
    error TEXT,
    execution_time_ms DOUBLE PRECISION,
    session_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS tool_invocations_tool_idx ON tool_invocations (tool_name, created_at DESC);
CREATE INDEX IF NOT EXISTS tool_invocations_session_idx ON tool_invocations (session_id);

-- ========== Agent 记忆向量索引 ==========
CREATE INDEX IF NOT EXISTS agent_memories_embedding_idx ON agent_memories
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS agent_memories_type_idx ON agent_memories (memory_type);
CREATE INDEX IF NOT EXISTS agent_memories_expires_idx ON agent_memories (expires_at)
    WHERE expires_at IS NOT NULL;