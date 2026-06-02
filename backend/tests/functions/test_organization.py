# backend/test_organization.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from app.services.organization_service import OrganizationService
from app.core.config import settings


async def test_organization():
    engine = create_async_engine(settings.database_url)
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        service = OrganizationService(session)

        # 1. 测试为未打标签的知识生成标签
        # print("=== 步骤1: 自动标签 ===")
        # tag_result = await service.organize_untagged(limit=10)
        # print(f"  处理: {tag_result['processed']} 条")
        # print(f"  打标签: {tag_result['tagged']} 条")

        # # 2. 测试生成摘要
        # print("\n=== 步骤2: 生成摘要 ===")
        # summary_result = await service.generate_summaries(limit=10)
        # print(f"  处理: {summary_result['processed']} 条")
        # print(f"  生成摘要: {summary_result['summarized']} 条")

        # # 3. 测试聚类
        # print("\n=== 步骤3: 知识聚类 ===")
        # cluster_result = await service.organize_clusters()
        # print(f"  生成聚类: {cluster_result['clusters_created']} 个")
        # for cluster in cluster_result["clusters"][:3]:
        #     print(f"    - {cluster['name']}: {cluster['knowledge_count']} 条")

        # # 4. 测试去重
        # print("\n=== 步骤4: 去重清理 ===")
        # dedup_result = await service.cleanup_duplicates(dry_run=True)
        # print(f"  将删除: {len(dedup_result['items_to_remove'])} 条")

        # 5. 生成报告
        print("\n=== 步骤5: 生成整理报告 ===")
        report = await service.generate_report()
        print(f"  总知识数: {report['total_knowledge']}")
        print(f"  标签覆盖率: {report['tag_coverage']}%")
        print(f"  聚类数: {report['cluster_count']}")
        print(f"  热门标签: {report['top_tags'][:3]}")


asyncio.run(test_organization())
