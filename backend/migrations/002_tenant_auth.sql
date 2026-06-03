-- 租户与用户、业务表租户隔离

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

CREATE INDEX IF NOT EXISTS users_tenant_idx ON users (tenant_id);

DROP TRIGGER IF EXISTS update_tenants_updated_at ON tenants;
CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 默认租户（迁移已有数据）
INSERT INTO tenants (id, name, slug)
VALUES ('00000000-0000-0000-0000-000000000001', '默认租户', 'default')
ON CONFLICT (slug) DO NOTHING;

-- knowledge 租户列
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS tenant_id UUID;
UPDATE knowledge SET tenant_id = '00000000-0000-0000-0000-000000000001'
WHERE tenant_id IS NULL;
ALTER TABLE knowledge ALTER COLUMN tenant_id SET NOT NULL;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'knowledge_tenant_fk'
    ) THEN
        ALTER TABLE knowledge
            ADD CONSTRAINT knowledge_tenant_fk
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
END $$;

ALTER TABLE knowledge DROP CONSTRAINT IF EXISTS knowledge_content_hash_key;
CREATE UNIQUE INDEX IF NOT EXISTS knowledge_tenant_content_hash_idx
    ON knowledge (tenant_id, content_hash)
    WHERE content_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS knowledge_tenant_created_idx
    ON knowledge (tenant_id, created_at DESC);

-- agent 会话
ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS user_id UUID;
UPDATE agent_sessions SET tenant_id = '00000000-0000-0000-0000-000000000001'
WHERE tenant_id IS NULL;
ALTER TABLE agent_sessions ALTER COLUMN tenant_id SET NOT NULL;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'agent_sessions_tenant_fk') THEN
        ALTER TABLE agent_sessions
            ADD CONSTRAINT agent_sessions_tenant_fk
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'agent_sessions_user_fk') THEN
        ALTER TABLE agent_sessions
            ADD CONSTRAINT agent_sessions_user_fk
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS agent_sessions_tenant_idx ON agent_sessions (tenant_id, updated_at DESC);

-- 待办按租户隔离
ALTER TABLE todos ADD COLUMN IF NOT EXISTS tenant_id UUID;
UPDATE todos SET tenant_id = '00000000-0000-0000-0000-000000000001'
WHERE tenant_id IS NULL;
ALTER TABLE todos ALTER COLUMN tenant_id SET NOT NULL;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'todos_tenant_fk') THEN
        ALTER TABLE todos
            ADD CONSTRAINT todos_tenant_fk
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS todos_tenant_idx ON todos (tenant_id, completed);
