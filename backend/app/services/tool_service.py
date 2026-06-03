"""工具调用服务：注册、列表、统一执行。"""

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.tools.init_tools import ensure_tools_initialized
from app.core.agent.tools.registry import get_tool_registry
from app.core.agent.tools.base import ToolStatus

logger = logging.getLogger(__name__)


class ToolService:
    def __init__(
        self, db_session: Optional[AsyncSession] = None, tenant_id=None
    ):
        self.db = db_session
        self.tenant_id = tenant_id

    async def setup(self) -> None:
        await ensure_tools_initialized(self.db, self.tenant_id)

    async def list_tools(self) -> list[dict[str, Any]]:
        await self.setup()
        return get_tool_registry().list_tools()

    async def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        await self.setup()
        registry = get_tool_registry()
        result = await registry.execute(tool_name, **params)
        payload = {
            "tool_name": tool_name,
            "success": result.status == ToolStatus.SUCCESS,
            "status": result.status.value,
            "data": result.data,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms,
        }
        await self._log_invocation(tool_name, params, payload, session_id)
        return payload

    async def _log_invocation(
        self,
        tool_name: str,
        params: dict[str, Any],
        payload: dict[str, Any],
        session_id: str | None,
    ) -> None:
        if not self.db:
            return
        try:
            from app.models.tool_log import ToolInvocation

            row = ToolInvocation(
                tool_name=tool_name,
                params=params,
                status=payload.get("status", "failed"),
                result=payload.get("data") if payload.get("success") else None,
                error=payload.get("error"),
                execution_time_ms=payload.get("execution_time_ms"),
                session_id=session_id,
            )
            self.db.add(row)
            await self.db.commit()
        except Exception as e:
            await self.db.rollback()
            logger.warning(f"Failed to log tool invocation: {e}")
