from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.services.knowledge_service import KnowledgeService
from app.models.knowledge import Knowledge
from app.models.response import APIResponse, success_response
from app.models.schemas import (
    KnowledgeCreate,
    KnowledgeUpdate,
    KnowledgeResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)

router = APIRouter()


def _to_response(knowledge: Knowledge) -> KnowledgeResponse:
    return KnowledgeResponse.model_validate(knowledge, from_attributes=True)


@router.post("/create", response_model=APIResponse[KnowledgeResponse])
async def create_knowledge(
    knowledge_in: KnowledgeCreate,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """创建知识条目"""
    service = KnowledgeService(db, current.tenant_id)
    return success_response(data=_to_response(await service.create(knowledge_in)))


@router.post("/batch", response_model=APIResponse[List[KnowledgeResponse]])
async def batch_create_knowledge(
    knowledge_list: List[KnowledgeCreate],
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """批量创建知识条目"""
    service = KnowledgeService(db, current.tenant_id)
    return success_response(
        data=[_to_response(k) for k in await service.create_batch(knowledge_list)]
    )


@router.post("/search", response_model=APIResponse[SearchResponse])
async def search_knowledge(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """语义搜索知识库"""
    import time

    start_time = time.time()

    service = KnowledgeService(db, current.tenant_id)
    results, total = await service.search_semantic(request)

    return success_response(
        data=SearchResponse(
            results=[
                SearchResult(
                    knowledge=_to_response(knowledge),
                    similarity_score=score,
                )
                for knowledge, score in results
            ],
            total=total,
            query_time_ms=(time.time() - start_time) * 1000,
        )
    )


@router.get("/recent", response_model=APIResponse[List[KnowledgeResponse]])
async def get_recent_knowledge(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """获取最近的知识条目"""
    service = KnowledgeService(db, current.tenant_id)
    return success_response(
        data=[_to_response(k) for k in await service.get_recent(days=days, limit=limit)]
    )


@router.get("/stats", response_model=APIResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """获取知识库统计信息"""
    service = KnowledgeService(db, current.tenant_id)
    return success_response(data=await service.get_stats())


@router.get("/{knowledge_id}", response_model=APIResponse[KnowledgeResponse])
async def get_knowledge(
    knowledge_id: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """获取单个知识条目"""
    service = KnowledgeService(db, current.tenant_id)
    knowledge = await service.get_by_id(knowledge_id)
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return success_response(data=_to_response(knowledge))


@router.put("/{knowledge_id}", response_model=APIResponse[KnowledgeResponse])
async def update_knowledge(
    knowledge_id: str,
    update_data: KnowledgeUpdate,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """更新知识条目"""
    service = KnowledgeService(db, current.tenant_id)
    knowledge = await service.update(knowledge_id, update_data)
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return success_response(data=_to_response(knowledge))


@router.delete("/{knowledge_id}", response_model=APIResponse)
async def delete_knowledge(
    knowledge_id: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    """删除知识条目"""
    service = KnowledgeService(db, current.tenant_id)
    success = await service.delete(knowledge_id)
    if not success:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return success_response(message="Deleted successfully")
