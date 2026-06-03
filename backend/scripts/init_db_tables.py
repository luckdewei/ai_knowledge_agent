#!/usr/bin/env python3
"""通过 ORM 创建所有表（开发环境备用，生产推荐 init.sql）。"""

import asyncio

from app.core.database import Base, engine
from app.models import (  # noqa: F401 — 注册所有模型
    Knowledge,
    Cluster,
    AgentMemory,
    TodoItem,
    KnowledgeRelation,
    AgentSession,
    ChatMessage,
    ToolInvocation,
)


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("All tables created (create_all).")


if __name__ == "__main__":
    asyncio.run(main())
