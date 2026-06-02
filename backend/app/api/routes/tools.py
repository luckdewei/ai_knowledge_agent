"""工具调用 API"""

from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.agent.tools import CalendarTool, TodoTool, EmailTool, SearchTool
from app.core.agent.tools.registry import get_tool_registry
from app.core.agent.tools.base import ToolStatus
from app.models.response import APIResponse, success_response, json_error_response

router = APIRouter(prefix="/tools", tags=["tools"])


class CalendarRequest(BaseModel):
    """日历操作请求"""

    action: str = Field(..., pattern="^(create|query|delete|freebusy)$")
    summary: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    event_id: Optional[str] = None
    days: int = 7
    description: Optional[str] = None
    location: Optional[str] = None


class TodoRequest(BaseModel):
    """待办操作请求"""

    action: str = Field(..., pattern="^(add|list|complete|delete|update)$")
    title: Optional[str] = None
    description: Optional[str] = None
    priority: int = Field(default=1, ge=1, le=5)
    due_date: Optional[str] = None
    category: Optional[str] = None
    todo_id: Optional[str] = None
    status: str = "pending"


class EmailRequest(BaseModel):
    """邮件操作请求"""

    action: str = Field(..., pattern="^(send|query)$")
    to: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    is_html: bool = False


class SearchRequest(BaseModel):
    """搜索请求"""

    query: str
    source: str = Field(default="both", pattern="^(web|knowledge|both)$")
    top_k: int = Field(default=5, ge=1, le=20)


@router.get("/list", response_model=APIResponse)
async def list_tools():
    """列出所有可用工具"""
    registry = get_tool_registry()
    return success_response(data=registry.list_tools())


@router.post("/calendar", response_model=APIResponse)
async def call_calendar(request: CalendarRequest, db: AsyncSession = Depends(get_db)):
    """调用日历工具"""
    tool = CalendarTool()
    result = await tool.execute(
        action=request.action,
        summary=request.summary,
        start_time=request.start_time,
        end_time=request.end_time,
        event_id=request.event_id,
        days=request.days,
        description=request.description,
        location=request.location,
    )

    if result.status == ToolStatus.SUCCESS:
        return success_response(data=result.data)

    return json_error_response(
        500, "日历工具执行失败", result.error, http_status=500
    )


@router.post("/todo", response_model=APIResponse)
async def call_todo(request: TodoRequest, db: AsyncSession = Depends(get_db)):
    """调用待办工具"""
    tool = TodoTool(db)
    result = await tool.execute(
        action=request.action,
        title=request.title,
        description=request.description,
        priority=request.priority,
        due_date=request.due_date,
        category=request.category,
        todo_id=request.todo_id,
        status=request.status,
    )

    if result.status == ToolStatus.SUCCESS:
        return success_response(data=result.data)

    return json_error_response(
        500, "待办工具执行失败", result.error, http_status=500
    )


@router.post("/email", response_model=APIResponse)
async def call_email(request: EmailRequest):
    """调用邮件工具"""
    tool = EmailTool()
    result = await tool.execute(
        action=request.action,
        to=request.to,
        subject=request.subject,
        body=request.body,
        is_html=request.is_html,
    )

    if result.status == ToolStatus.SUCCESS:
        return success_response(data=result.data)

    return json_error_response(
        500, "邮件工具执行失败", result.error, http_status=500
    )


@router.post("/search", response_model=APIResponse)
async def call_search(request: SearchRequest, db: AsyncSession = Depends(get_db)):
    """调用搜索工具"""
    tool = SearchTool(db)
    result = await tool.execute(
        query=request.query, source=request.source, top_k=request.top_k
    )

    if result.status == ToolStatus.SUCCESS:
        return success_response(data=result.data)

    return json_error_response(
        500, "搜索工具执行失败", result.error, http_status=500
    )
