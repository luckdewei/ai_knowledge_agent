# backend/test_tagging.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.services.tagging_service import TaggingService
from app.core.config import settings


async def test_tagging():
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        service = TaggingService(db_session=session)

        # 测试 LLM 标签生成
        print("=== 测试 LLM 标签生成 ===")
        content = (
            "LangGraph 是用于构建有状态的多角色应用的库，它扩展了 LangChain 的功能。"
        )
        tags = await service.generate_tags(
            content, title="LangGraph 介绍", method="llm"
        )
        print(f"LLM 生成的标签: {tags}")

        # 测试混合策略
        print("\n=== 测试混合策略 ===")
        hybrid_tags = await service.generate_tags(content, method="hybrid")
        print(f"混合策略生成的标签: {hybrid_tags}")

        # 测试为未打标签的知识生成标签
        print("\n=== 测试为未打标签知识生成标签 ===")
        suggestions = await service.suggest_tags_for_untagged(limit=5)
        for s in suggestions:
            print(f"  {s['title'][:30]}... -> {s['suggested_tags']}")

        # 测试标签统计
        print("\n=== 测试标签统计 ===")
        stats = await service.get_tag_stats(limit=10)
        for stat in stats:
            print(f"  {stat['tag']}: {stat['count']} 次")


asyncio.run(test_tagging())
