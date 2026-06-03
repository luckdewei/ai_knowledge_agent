"""租户数据隔离辅助。"""

import uuid

from app.models.knowledge import Knowledge


def tenant_knowledge_filter(tenant_id: uuid.UUID):
    return Knowledge.tenant_id == tenant_id
