from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from app.core.config import settings
from app.api.routes import health, knowledge, agent, tools

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

    yield

    # Shutdown: 清理资源
    logger.info("Shutting down application")
    # await close_database()


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
    # app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
    # app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
    # app.include_router(tools.router, prefix="/api/tools", tags=["tools"])

    # 全局异常处理
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "type": type(exc).__name__},
        )

    return app


# 创建应用实例
app = create_app()


# 直接运行时的入口 (python -m app.main)
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host=settings.host, port=settings.port, reload=settings.debug
    )
