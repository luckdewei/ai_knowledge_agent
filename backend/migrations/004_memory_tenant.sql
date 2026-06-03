-- Agent 记忆按租户/用户隔离

ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS tenant_id UUID;
ALTER TABLE agent_memories ADD COLUMN IF NOT EXISTS user_id UUID;

UPDATE agent_memories
SET tenant_id = '00000000-0000-0000-0000-000000000001'
WHERE tenant_id IS NULL;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'agent_memories_tenant_fk') THEN
        ALTER TABLE agent_memories
            ADD CONSTRAINT agent_memories_tenant_fk
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'agent_memories_user_fk') THEN
        ALTER TABLE agent_memories
            ADD CONSTRAINT agent_memories_user_fk
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS agent_memories_tenant_type_idx
    ON agent_memories (tenant_id, memory_type, created_at DESC);

CREATE INDEX IF NOT EXISTS agent_memories_tenant_session_idx
    ON agent_memories (tenant_id, ((context->>'session_id')));
