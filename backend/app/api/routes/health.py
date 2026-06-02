from fastapi import APIRouter

from app.core.config import settings
from app.models.response import APIResponse, success_response

router = APIRouter()


@router.get("/", response_model=APIResponse)
async def health_check():
    """健康检查接口"""
    return success_response(
        data={
            "status": "healthy",
            "version": settings.app_version,
        }
    )


@router.get("/ready", response_model=APIResponse)
async def readiness_check():
    """就绪检查（检查依赖服务是否可用）"""
    return success_response(data={"ready": True})
