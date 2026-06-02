"""
待办事项工具

管理本地待办事项
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseTool, ToolResult, ToolStatus, ToolParameter
from app.models.todo import TodoItem

logger = logging.getLogger(__name__)


class TodoTool(BaseTool):
    """待办事项工具"""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    @property
    def name(self) -> str:
        return "todo"

    @property
    def description(self) -> str:
        return "管理待办事项，支持创建、查询、完成、删除操作"

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型: add, list, complete, delete, update",
                required=True,
                enum=["add", "list", "complete", "delete", "update"],
            ),
            ToolParameter(
                name="title", type="string", description="待办标题", required=False
            ),
            ToolParameter(
                name="description",
                type="string",
                description="待办描述",
                required=False,
            ),
            ToolParameter(
                name="priority", type="number", description="优先级 1-5", required=False
            ),
            ToolParameter(
                name="due_date",
                type="string",
                description="截止日期 (ISO 格式)",
                required=False,
            ),
            ToolParameter(
                name="category", type="string", description="分类", required=False
            ),
            ToolParameter(
                name="todo_id", type="string", description="待办 ID", required=False
            ),
            ToolParameter(
                name="status",
                type="string",
                description="状态过滤: pending, completed, all",
                required=False,
                default="pending",
            ),
        ]

    async def execute(self, **kwargs) -> ToolResult:
        """执行待办操作"""
        action = kwargs.get("action")

        try:
            if action == "add":
                return await self._add_todo(kwargs)
            elif action == "list":
                return await self._list_todos(kwargs)
            elif action == "complete":
                return await self._complete_todo(kwargs)
            elif action == "delete":
                return await self._delete_todo(kwargs)
            elif action == "update":
                return await self._update_todo(kwargs)
            else:
                return ToolResult(
                    status=ToolStatus.FAILED, error=f"Unknown action: {action}"
                )
        except Exception as e:
            logger.error(f"Todo operation failed: {e}")
            return ToolResult(status=ToolStatus.FAILED, error=str(e))

    async def _add_todo(self, params: Dict) -> ToolResult:
        """添加待办"""
        title = params.get("title")
        if not title:
            return ToolResult(
                status=ToolStatus.FAILED, error="Missing required parameter: title"
            )

        todo = TodoItem(
            title=title,
            description=params.get("description"),
            priority=params.get("priority", 1),
            category=params.get("category"),
        )

        due_date = params.get("due_date")
        if due_date:
            todo.due_date = datetime.fromisoformat(due_date)

        self.db.add(todo)
        await self.db.commit()
        await self.db.refresh(todo)

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=todo.to_dict(),
            metadata={"action": "add_todo"},
        )

    async def _list_todos(self, params: Dict) -> ToolResult:
        """列出待办"""
        status_filter = params.get("status", "pending")

        stmt = select(TodoItem)

        if status_filter == "pending":
            stmt = stmt.where(TodoItem.completed == False)
        elif status_filter == "completed":
            stmt = stmt.where(TodoItem.completed == True)

        stmt = stmt.order_by(TodoItem.priority.desc(), TodoItem.due_date)

        result = await self.db.execute(stmt)
        todos = result.scalars().all()

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"total": len(todos), "todos": [t.to_dict() for t in todos]},
            metadata={"action": "list_todos", "status_filter": status_filter},
        )

    async def _complete_todo(self, params: Dict) -> ToolResult:
        """完成待办"""
        todo_id = params.get("todo_id")

        if not todo_id:
            return ToolResult(
                status=ToolStatus.FAILED, error="Missing required parameter: todo_id"
            )

        stmt = select(TodoItem).where(TodoItem.id == todo_id)
        result = await self.db.execute(stmt)
        todo = result.scalar_one_or_none()

        if not todo:
            return ToolResult(
                status=ToolStatus.FAILED, error=f"Todo not found: {todo_id}"
            )

        todo.completed = True
        await self.db.commit()

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=todo.to_dict(),
            metadata={"action": "complete_todo"},
        )

    async def _delete_todo(self, params: Dict) -> ToolResult:
        """删除待办"""
        todo_id = params.get("todo_id")

        if not todo_id:
            return ToolResult(
                status=ToolStatus.FAILED, error="Missing required parameter: todo_id"
            )

        stmt = delete(TodoItem).where(TodoItem.id == todo_id)
        await self.db.execute(stmt)
        await self.db.commit()

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={"deleted": True, "todo_id": todo_id},
            metadata={"action": "delete_todo"},
        )

    async def _update_todo(self, params: Dict) -> ToolResult:
        """更新待办"""
        todo_id = params.get("todo_id")

        if not todo_id:
            return ToolResult(
                status=ToolStatus.FAILED, error="Missing required parameter: todo_id"
            )

        stmt = select(TodoItem).where(TodoItem.id == todo_id)
        result = await self.db.execute(stmt)
        todo = result.scalar_one_or_none()

        if not todo:
            return ToolResult(
                status=ToolStatus.FAILED, error=f"Todo not found: {todo_id}"
            )

        if params.get("title"):
            todo.title = params["title"]
        if params.get("description") is not None:
            todo.description = params["description"]
        if params.get("priority"):
            todo.priority = params["priority"]
        if params.get("category") is not None:
            todo.category = params["category"]
        if params.get("due_date"):
            todo.due_date = datetime.fromisoformat(params["due_date"])

        await self.db.commit()
        await self.db.refresh(todo)

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=todo.to_dict(),
            metadata={"action": "update_todo"},
        )
