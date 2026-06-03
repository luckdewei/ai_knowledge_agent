from fastapi import APIRouter

from app.core.config import settings
from app.core.cache import cache_status
from app.core.redis_client import redis_ping
from app.models.response import APIResponse, success_response

router = APIRouter()


@router.get("/", response_model=APIResponse)
async def health_check():
    """健康检查接口"""
    return success_response(
        data={
            "status": "healthy",
            "version": settings.app_version,
            "cache": cache_status(),
        }
    )


@router.get("/ready", response_model=APIResponse)
async def readiness_check():
    """就绪检查（含 Redis 连通性，Redis 关闭或未连接时仍返回 ready）"""
    redis_ok = await redis_ping() if settings.redis_enabled else None
    return success_response(
        data={
            "ready": True,
            "redis": redis_ok,
            "cache": cache_status(),
        }
    )
