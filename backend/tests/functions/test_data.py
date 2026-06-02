"""添加测试数据用于验收"""

import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.models.knowledge import Knowledge
from app.core.config import settings
from app.core.vector.embeddings import embeddings_service
from app.services.knowledge_service import KnowledgeService

# 测试数据
TEST_KNOWLEDGE = [
    {
        "title": "Python 异步编程入门",
        "content": "asyncio 是 Python 的异步编程库，使用 async/await 语法。事件循环是 asyncio 的核心。",
        "tags": ["Python", "编程"],
        "source_type": "test",
    },
    {
        "title": "FastAPI 性能优化",
        "content": "FastAPI 基于 Starlette，性能接近 Go。使用 async 函数可以获得更好的并发性能。",
        "tags": ["FastAPI", "Python"],
        "source_type": "test",
    },
    {
        "title": "机器学习基础概念",
        "content": "监督学习、无监督学习、强化学习是机器学习的三大范式。",
        "tags": ["AI", "机器学习"],
        "source_type": "test",
    },
    {
        "title": "深度学习与神经网络",
        "content": "神经网络由输入层、隐藏层、输出层组成。反向传播是训练的核心算法。",
        "tags": ["AI", "深度学习"],
        "source_type": "test",
    },
    {
        "title": "项目管理的五大过程组",
        "content": "启动、规划、执行、监控、收尾是项目管理的五大过程组。",
        "tags": ["项目管理"],
        "source_type": "test",
    },
    {
        "title": "敏捷开发实践",
        "content": "Scrum 框架包含 Sprint 计划、每日站会、Sprint 评审和回顾。",
        "tags": ["项目管理", "敏捷"],
        "source_type": "test",
    },
    # 与第一条 content 完全相同；content_hash 有唯一约束，脚本会跳过并提示
    {
        "title": "Python 异步编程入门（重复）",
        "content": "asyncio 是 Python 的异步编程库，使用 async/await 语法。事件循环是 asyncio 的核心。",
        "tags": None,
        "source_type": "test",
    },
]


async def add_test_data():
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    added = 0
    skipped = 0

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Knowledge.content_hash).where(Knowledge.content_hash.is_not(None))
            )
            existing_hashes = set(result.scalars().all())
            seen_hashes: set[str] = set()

            for data in TEST_KNOWLEDGE:
                content_hash = KnowledgeService.compute_content_hash(data["content"])

                if content_hash in existing_hashes or content_hash in seen_hashes:
                    skipped += 1
                    print(f"Skip (duplicate hash): {data['title']}")
                    continue

                embedding = await embeddings_service.embed_query(data["content"])

                knowledge = Knowledge(
                    title=data["title"],
                    content=data["content"],
                    content_hash=content_hash,
                    source_type=data["source_type"],
                    tags=data.get("tags"),
                    embedding=embedding,
                )
                session.add(knowledge)
                seen_hashes.add(content_hash)
                added += 1

            if added:
                await session.commit()

            print(
                f"Done: added {added}, skipped {skipped} "
                f"(total in fixture: {len(TEST_KNOWLEDGE)})"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(add_test_data())
