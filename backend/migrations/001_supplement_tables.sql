-- 增量迁移：补充 todos / 关系 / 会话 / 工具日志等表
-- 用法:
--   docker exec -i pka-postgres psql -U postgres -d knowledge_db < backend/migrations/001_supplement_tables.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 待办
CREATE TABLE IF NOT EXISTS todos (
    id VARCHAR(36) PRIMARY KEY,
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
DROP TRIGGER IF EXISTS update_todos_updated_at ON todos;
CREATE TRIGGER update_todos_updated_at
    BEFORE UPDATE ON todos FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 知识关系
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

-- Agent 会话
CREATE TABLE IF NOT EXISTS agent_sessions (
    id VARCHAR(64) PRIMARY KEY,
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
DROP TRIGGER IF EXISTS update_agent_sessions_updated_at ON agent_sessions;
CREATE TRIGGER update_agent_sessions_updated_at
    BEFORE UPDATE ON agent_sessions FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 工具调用日志
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

-- 聚类表 updated_at 触发器（若不存在）
DROP TRIGGER IF EXISTS update_clusters_updated_at ON clusters;
CREATE TRIGGER update_clusters_updated_at
    BEFORE UPDATE ON clusters FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Agent 记忆索引（若不存在）
CREATE INDEX IF NOT EXISTS agent_memories_embedding_idx ON agent_memories
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS agent_memories_type_idx ON agent_memories (memory_type);
