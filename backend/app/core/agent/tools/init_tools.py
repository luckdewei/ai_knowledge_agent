"""
工具初始化

在应用启动时注册所有可用工具
"""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .registry import get_tool_registry
from .calendar_tool import CalendarTool
from .todo_tool import TodoTool
from .email_tool import EmailTool
from .search_tool import SearchTool

logger = logging.getLogger(__name__)


async def init_tools(db_session: Optional[AsyncSession] = None):
    """
    初始化并注册所有工具

    Args:
        db_session: 数据库会话（用于需要数据库的工具）
    """
    registry = get_tool_registry()

    # 注册日历工具（需要 Google Calendar 凭证）
    try:
        registry.register(CalendarTool(), rate_limit=30)  # 每分钟30次
        logger.info("CalendarTool registered")
    except Exception as e:
        logger.warning(f"Failed to register CalendarTool: {e}")

    # 注册待办工具（需要数据库）
    if db_session:
        registry.register(TodoTool(db_session), rate_limit=60)
        logger.info("TodoTool registered")

    # 注册邮件工具
    try:
        registry.register(EmailTool(), rate_limit=20)
        logger.info("EmailTool registered")
    except Exception as e:
        logger.warning(f"Failed to register EmailTool: {e}")

    # 注册搜索工具（需要数据库）
    if db_session:
        registry.register(SearchTool(db_session), rate_limit=30)
        logger.info("SearchTool registered")

    logger.info(f"Tool registry initialized with {len(registry.list_tools())} tools")


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

    return {
        "success": result.status == "success",
        "data": result.data,
        "error": result.error,
        "execution_time_ms": result.execution_time_ms,
    }
