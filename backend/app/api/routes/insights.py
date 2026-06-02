from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.relation_service import RelationDiscoveryService
from app.services.trend_service import TrendAnalysisService
from app.services.recommendation_service import KnowledgeRecommendationService
from app.services.reminder_service import ActiveReminderService
from app.services.memory_service import MemoryService

router = APIRouter()


@router.get("/relations/{knowledge_id}")
async def get_relations(knowledge_id: str, db: AsyncSession = Depends(get_db)):
    """获取知识的关系网络"""
    service = RelationDiscoveryService(db)
    await service.discover_all_relations()
    return service.get_related_knowledge(knowledge_id)


@router.get("/trends/activity")
async def get_activity_trend(days: int = 90, db: AsyncSession = Depends(get_db)):
    """获取活跃度趋势"""
    service = TrendAnalysisService(db)
    return await service.get_activity_trend(days)


@router.get("/trends/attention")
async def get_attention_shift(days: int = 90, db: AsyncSession = Depends(get_db)):
    """获取关注点变化"""
    service = TrendAnalysisService(db)
    return await service.analyze_attention_shift(days)


@router.get("/recommendations/{knowledge_id}")
async def get_recommendations(
    knowledge_id: str, limit: int = 5, db: AsyncSession = Depends(get_db)
):
    """获取相关知识推荐"""
    service = KnowledgeRecommendationService(db)
    return await service.recommend_related(knowledge_id, limit)


@router.get("/network/{knowledge_id}")
async def get_knowledge_network(
    knowledge_id: str, depth: int = 2, db: AsyncSession = Depends(get_db)
):
    """获取知识关系网络（可视化用）"""
    service = KnowledgeRecommendationService(db)
    return await service.get_knowledge_network(knowledge_id, depth)


@router.get("/reminders")
async def get_reminders(db: AsyncSession = Depends(get_db)):
    """获取主动提醒"""
    service = ActiveReminderService(db)
    return await service.generate_reminders()


@router.get("/insight/{knowledge_id}")
async def get_personalized_insight(
    knowledge_id: str, db: AsyncSession = Depends(get_db)
):
    """获取个性化洞察"""
    service = ActiveReminderService(db)
    return {"insight": await service.get_personalized_insight(knowledge_id)}
