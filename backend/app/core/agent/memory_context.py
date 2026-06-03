"""将 Agent 记忆注入对话上下文。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory_service import MemoryService


def format_memory_addon(relevant_memories: list[dict[str, Any]]) -> str:
    if not relevant_memories:
        return ""
    lines = [
        "## 与用户相关的历史记忆",
        "（请结合以下信息回答；未在记忆中的内容不要编造。）",
    ]
    for i, m in enumerate(relevant_memories, 1):
        lines.append(f"{i}. {m.get('content', '')}")
    return "\n\n".join(lines)


async def load_memory_for_query(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    session_id: str,
    query: str,
    use_memory: bool,
    limit: int = 5,
) -> tuple[str, list[dict[str, Any]]]:
    if not use_memory:
        return "", []
    svc = MemoryService(db, tenant_id, user_id)
    ctx = await svc.get_memory_context(session_id, query, limit=limit)
    memories = ctx.get("relevant_memories") or []
    return format_memory_addon(memories), memories


def append_memory_to_system(system: str, addon: str) -> str:
    if not addon.strip():
        return system
    return f"{system.rstrip()}\n\n{addon}"
