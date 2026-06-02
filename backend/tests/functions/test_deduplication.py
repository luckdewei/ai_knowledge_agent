# backend/test_deduplication.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.services.deduplication_service import DeduplicationService
from app.core.config import settings


async def test_deduplication():
    engine = create_async_engine(settings.database_url)
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        service = DeduplicationService(session)

        # 测试精确重复查找
        print("=== 测试精确重复查找 ===")
        exact_dups = await service.find_exact_duplicates()
        for dup in exact_dups:
            print(f"  哈希 {dup['hash'][:8]}... 有 {dup['count']} 条重复")
            print(f"    IDs: {dup['ids']}")

        # 测试相似重复查找
        print("\n=== 测试相似重复查找 ===")
        similar_dups = await service.find_similar_duplicates(threshold=0.85)
        for dup in similar_dups:
            print(f"  相似组包含 {dup['count']} 条")
            print(f"    IDs: {dup['ids']}")

        # 测试去重（dry_run 模式）
        print("\n=== 测试去重（预览模式）===")
        result = await service.remove_duplicates(keep_oldest=True, dry_run=True)
        print(f"  精确重复组数: {result['exact_duplicates_found']}")
        print(f"  相似重复组数: {result['similar_duplicates_found']}")
        print(f"  将删除: {len(result['items_to_remove'])} 条")

        # 测试实际去重（谨慎！）
        print("\n=== 测试实际去重 ===")
        confirm = input("是否执行实际去重？(y/N): ")
        if confirm.lower() == "y":
            result = await service.remove_duplicates(keep_oldest=True, dry_run=False)
            print(f"  实际删除: {result['items_removed']} 条")


asyncio.run(test_deduplication())
