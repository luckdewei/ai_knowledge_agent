from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.core.database import get_db
from app.services.knowledge_service import KnowledgeService
from app.models.schemas import (
    KnowledgeCreate,
    KnowledgeUpdate,
    KnowledgeResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)

router = APIRouter()


@router.post("/create", response_model=KnowledgeResponse)
async def create_knowledge(
    knowledge_in: KnowledgeCreate, db: AsyncSession = Depends(get_db)
):
    """创建知识条目"""
    service = KnowledgeService(db)
    return await service.create(knowledge_in)


@router.post("/batch", response_model=List[KnowledgeResponse])
async def batch_create_knowledge(
    knowledge_list: List[KnowledgeCreate], db: AsyncSession = Depends(get_db)
):
    """批量创建知识条目"""
    service = KnowledgeService(db)
    return await service.create_batch(knowledge_list)


@router.get("/{knowledge_id}", response_model=KnowledgeResponse)
async def get_knowledge(knowledge_id: str, db: AsyncSession = Depends(get_db)):
    """获取单个知识条目"""
    service = KnowledgeService(db)
    knowledge = await service.get_by_id(knowledge_id)
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return knowledge


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(request: SearchRequest, db: AsyncSession = Depends(get_db)):
    """语义搜索知识库"""
    import time

    start_time = time.time()

    service = KnowledgeService(db)
    results, total = await service.search_semantic(request)

    return SearchResponse(
        results=[
            SearchResult(
                knowledge=KnowledgeResponse.model_validate(knowledge.to_dict()),
                similarity_score=score,
            )
            for knowledge, score in results
        ],
        total=total,
        query_time_ms=(time.time() - start_time) * 1000,
    )


@router.get("/recent", response_model=List[KnowledgeResponse])
async def get_recent_knowledge(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """获取最近的知识条目"""
    service = KnowledgeService(db)
    return await service.get_recent(days=days, limit=limit)


@router.put("/{knowledge_id}", response_model=KnowledgeResponse)
async def update_knowledge(
    knowledge_id: str, update_data: KnowledgeUpdate, db: AsyncSession = Depends(get_db)
):
    """更新知识条目"""
    service = KnowledgeService(db)
    knowledge = await service.update(knowledge_id, update_data)
    if not knowledge:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return knowledge


@router.delete("/{knowledge_id}")
async def delete_knowledge(knowledge_id: str, db: AsyncSession = Depends(get_db)):
    """删除知识条目"""
    service = KnowledgeService(db)
    success = await service.delete(knowledge_id)
    if not success:
        raise HTTPException(status_code=404, detail="Knowledge not found")
    return {"message": "Deleted successfully"}


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """获取知识库统计信息"""
    service = KnowledgeService(db)
    return await service.get_stats()
