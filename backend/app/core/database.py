"""
数据库核心模块。

负责三件事：
1. 定义 ORM 基类 Base，供所有数据模型继承
2. 创建全局异步数据库引擎和会话工厂
3. 提供 FastAPI 依赖注入函数 get_db，在请求生命周期内管理会话

连接串来自 app.core.config.settings.database_url，
默认格式：postgresql+asyncpg://user:pass@host:port/dbname
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, declared_attr
from sqlalchemy import JSON, String, Text, DateTime, Float, Index, func
from typing import Any
import uuid

from app.core.config import settings


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# 异步引擎（Engine）
# ---------------------------------------------------------------------------
# Engine 是 SQLAlchemy 与数据库之间的连接池管理器。
# 使用 asyncpg 驱动时，URL 必须以 postgresql+asyncpg:// 开头。
engine = create_async_engine(
    # 数据库连接串，可通过环境变量或 .env 覆盖
    settings.database_url,
    # debug=True 时在控制台打印每条 SQL，便于开发调试
    echo=settings.debug,
    # 连接池常驻连接数；并发请求高时可适当调大
    pool_size=10,
    # 超出 pool_size 时最多额外创建的临时连接数
    max_overflow=20,
    # 每次从池中取连接前先 ping 数据库，避免用到已断开的连接
    pool_pre_ping=True,
)

# ---------------------------------------------------------------------------
# 异步会话工厂（Session Factory）
# ---------------------------------------------------------------------------
# async_sessionmaker 不直接操作数据库，而是按需生产 AsyncSession 实例。
# 每个请求/业务单元应使用独立 session，用完即关，避免连接泄漏。
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    # commit 后对象属性仍可直接读取，无需 refresh；
    # 适合 FastAPI 在返回响应前还要读 ORM 对象字段的场景
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖注入：为每个请求提供数据库会话。

    用法示例（路由中）::
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()

    生命周期：
    - 请求进入时：创建 session 并通过 yield 交给路由处理函数
    - 请求结束时：finally 中关闭 session，连接归还连接池

    返回 AsyncGenerator 而非 AsyncSession，是因为函数体内使用了 yield，
    类型检查器（basedpyright）要求标注为生成器类型。
    """
    async with AsyncSessionLocal() as session:
        yield session
