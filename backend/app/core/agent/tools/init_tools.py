"""
工具初始化

在应用启动时注册所有可用工具
"""

import logging
import os
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .registry import get_tool_registry
from .calendar_tool import CalendarTool
from .todo_tool import TodoTool
from .email_tool import EmailTool
from .search_tool import SearchTool
from .save_knowledge_tool import SaveKnowledgeTool

logger = logging.getLogger(__name__)


async def init_tools(
    db_session: Optional[AsyncSession] = None, tenant_id=None
):
    """
    初始化并注册所有工具

    Args:
        db_session: 数据库会话（用于需要数据库的工具）
    """
    registry = get_tool_registry()

    # 日历工具需 credentials.json，缺失时跳过以免拖慢每次请求
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    if os.path.isfile(creds_path) or os.path.isfile("token.json"):
        try:
            registry.register(CalendarTool(credentials_path=creds_path), rate_limit=30)
            logger.info("CalendarTool registered")
        except Exception as e:
            logger.warning(f"Failed to register CalendarTool: {e}")
    else:
        logger.debug("CalendarTool skipped: no Google credentials")

    if db_session and tenant_id:
        registry.register(TodoTool(db_session, tenant_id), rate_limit=60)
        registry.register(SearchTool(db_session, tenant_id), rate_limit=30)
        registry.register(SaveKnowledgeTool(db_session, tenant_id), rate_limit=30)
        logger.info("Todo, Search & SaveKnowledge tools registered with db session")

    try:
        registry.register(EmailTool(), rate_limit=20)
        logger.info("EmailTool registered")
    except Exception as e:
        logger.warning(f"Failed to register EmailTool: {e}")

    logger.info(f"Tool registry initialized with {len(registry.list_tools())} tools")


async def ensure_tools_initialized(
    db_session: Optional[AsyncSession] = None, tenant_id=None
):
    """每次请求前确保工具已注册（数据库类工具绑定当前 session）。"""
    await init_tools(db_session, tenant_id)


def get_available_tools() -> list:
    """获取所有已注册工具的信息"""
    registry = get_tool_registry()
    return registry.list_tools()


async def execute_tool(tool_name: str, **kwargs) -> dict:
    """
    执行工具（便捷函数）

    Args:
        tool_name: 工具名称
        **kwargs: 工具参数

    Returns:
        执行结果
    """
    registry = get_tool_registry()
    result = await registry.execute(tool_name, **kwargs)

    from app.core.agent.tools.base import ToolStatus

    return {
        "success": result.status == ToolStatus.SUCCESS,
        "data": result.data,
        "error": result.error,
        "execution_time_ms": result.execution_time_ms,
    }
