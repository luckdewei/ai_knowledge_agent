from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from app.core.config import settings
from app.models.response import error_response
from app.api.routes import (
    health,
    insights,
    knowledge,
    agent,
    organization,
    tools,
    ingestion,
)
from app.core.scheduler import get_scheduler
from app.core.agent.tools.init_tools import init_tools
from app.core.database import engine, AsyncSessionLocal

# 配置日志
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    - startup: 初始化数据库连接、Agent 实例等
    - shutdown: 清理资源
    """
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # Startup: 这里会初始化数据库连接池、加载 Agent 等
    # await init_database()
    # await init_agent()

    # 初始化工具注册表
    async with AsyncSessionLocal() as session:
        await init_tools(session)

    # 启动定时调度器
    scheduler = get_scheduler()
    scheduler.start()

    yield

    # Shutdown: 清理资源
    scheduler.shutdown()
    # 关闭数据库连接
    await engine.dispose()
    logger.info("Shutting down application")


def create_app() -> FastAPI:
    """应用工厂函数"""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="智能个人知识库助手 API",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # CORS 配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(health.router, prefix="/api/health", tags=["health"])
    app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
    app.include_router(ingestion.router, prefix="/api/ingestion", tags=["ingestion"])
    app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
    app.include_router(
        organization.router, prefix="/api/organization", tags=["organization"]
    )
    app.include_router(insights.router, prefix="/api/insights", tags=["insights"])
    app.include_router(tools.router, prefix="/api/tools", tags=["tools"])

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(
                code=exc.status_code, message=detail, detail=detail
            ).model_dump(),
        )

    # 全局异常处理
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content=error_response(
                code=500,
                message="Internal server error",
                detail=str(exc) if settings.debug else None,
            ).model_dump(),
        )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        import time

        start_time = time.time()
        response = await call_next(request)
        duration = (time.time() - start_time) * 1000
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {duration:.2f}ms"
        )
        return response

    return app


# 创建应用实例
app = create_app()


# 直接运行时的入口 (python -m app.main)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host=settings.host, port=settings.port, reload=settings.debug
    )
