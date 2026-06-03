from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.models.response import APIResponse, success_response
from app.services.trend_service import TrendAnalysisService
from app.services.recommendation_service import KnowledgeRecommendationService
from app.services.reminder_service import ActiveReminderService

router = APIRouter()


def _trend(db: AsyncSession, current: CurrentUser) -> TrendAnalysisService:
    return TrendAnalysisService(db, current.tenant_id)


def _recommend(db: AsyncSession, current: CurrentUser) -> KnowledgeRecommendationService:
    return KnowledgeRecommendationService(db, current.tenant_id)


@router.get("/relations/{knowledge_id}", response_model=APIResponse)
async def get_relations(
    knowledge_id: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    service = _recommend(db, current)
    return success_response(
        data=await service.recommend_related(knowledge_id, limit=10)
    )


@router.get("/trends/activity", response_model=APIResponse)
async def get_activity_trend(
    days: int = 90,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    return success_response(data=await _trend(db, current).get_activity_trend(days))


@router.get("/trends/attention", response_model=APIResponse)
async def get_attention_shift(
    days: int = 90,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    return success_response(
        data=await _trend(db, current).analyze_attention_shift(days)
    )


@router.get("/recommendations/{knowledge_id}", response_model=APIResponse)
async def get_recommendations(
    knowledge_id: str,
    limit: int = 5,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    service = _recommend(db, current)
    return success_response(
        data=await service.recommend_related(knowledge_id, limit)
    )


@router.get("/network/{knowledge_id}", response_model=APIResponse)
async def get_knowledge_network(
    knowledge_id: str,
    depth: int = 2,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    service = _recommend(db, current)
    return success_response(
        data=await service.get_knowledge_network(knowledge_id, depth)
    )


@router.get("/reminders", response_model=APIResponse)
async def get_reminders(
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    service = ActiveReminderService(db, current.tenant_id)
    return success_response(data=await service.generate_reminders())


@router.get("/insight/{knowledge_id}", response_model=APIResponse)
async def get_personalized_insight(
    knowledge_id: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    service = ActiveReminderService(db, current.tenant_id)
    return success_response(
        data={"insight": await service.get_personalized_insight(knowledge_id)}
    )
