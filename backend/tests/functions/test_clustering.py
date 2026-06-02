# backend/test_clustering.py
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.services.clustering_service import ClusteringService
from app.core.config import settings


async def test_clustering():
    engine = create_async_engine(settings.database_url)
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with async_session() as session:
            service = ClusteringService(db_session=session)

            # 测试 KMeans 聚类
            print("=== 测试 KMeans 聚类 ===")
            clusters = await service.cluster_kmeans(n_clusters=3)

            for cluster in clusters:
                print(f"\n聚类: {cluster['name']}")
                print(f"  关键词: {cluster['keywords']}")
                print(f"  包含 {cluster['knowledge_count']} 条知识")
                description = cluster.get("description") or ""
                preview = description[:100] + ("..." if len(description) > 100 else "")
                print(f"  描述: {preview}")

            print(f"\n共生成 {len(clusters)} 个聚类")

            # 测试 DBSCAN 聚类
            print("\n=== 测试 DBSCAN 聚类 ===")
            dbscan_clusters = await service.cluster_dbscan(eps=0.5, min_samples=2)
            print(f"DBSCAN 生成 {len(dbscan_clusters)} 个聚类")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_clustering())
