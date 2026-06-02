from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.response import APIResponse, success_response
from app.services.organization_service import OrganizationService

router = APIRouter()


@router.post("/untagged", response_model=APIResponse)
async def organize_untagged(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """为未打标签的知识生成标签"""
    service = OrganizationService(db)
    return success_response(data=await service.organize_untagged(limit))


@router.post("/clusters", response_model=APIResponse)
async def organize_clusters(db: AsyncSession = Depends(get_db)):
    """执行知识聚类"""
    service = OrganizationService(db)
    return success_response(data=await service.organize_clusters())


@router.post("/summaries", response_model=APIResponse)
async def generate_summaries(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """生成摘要"""
    service = OrganizationService(db)
    return success_response(data=await service.generate_summaries(limit))


@router.post("/cleanup", response_model=APIResponse)
async def cleanup_duplicates(dry_run: bool = True, db: AsyncSession = Depends(get_db)):
    """清理重复内容"""
    service = OrganizationService(db)
    return success_response(data=await service.cleanup_duplicates(dry_run=dry_run))


@router.post("/full", response_model=APIResponse)
async def full_organization(
    background_tasks: BackgroundTasks,
    dry_run: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """完整知识整理（可后台执行）"""
    service = OrganizationService(db)

    if background_tasks:
        background_tasks.add_task(service.full_organization, dry_run)
        return success_response(
            data={"dry_run": dry_run},
            message="Organization started in background",
        )

    return success_response(data=await service.full_organization(dry_run))


@router.get("/report", response_model=APIResponse)
async def get_organization_report(db: AsyncSession = Depends(get_db)):
    """获取整理报告"""
    service = OrganizationService(db)
    return success_response(data=await service.generate_report())
