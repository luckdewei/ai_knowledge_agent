from fastapi import APIRouter
from datetime import datetime

router = APIRouter()


@router.get("/")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "0.1.0",
    }


@router.get("/ready")
async def readiness_check():
    """就绪检查（检查依赖服务是否可用）"""
    # 这里可以检查数据库连接、LLM API 等
    return {"ready": True}
