"""工具调用 API（需登录，按租户隔离）。"""

from typing import Any, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.models.response import APIResponse, success_response, json_error_response
from app.services.tool_service import ToolService

router = APIRouter()


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., description="工具名: search | todo | calendar | email")
    params: dict[str, Any] = Field(default_factory=dict)


class CalendarRequest(BaseModel):
    action: str = Field(..., pattern="^(create|query|delete|freebusy)$")
    summary: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    event_id: Optional[str] = None
    days: int = 7
    description: Optional[str] = None
    location: Optional[str] = None


class TodoRequest(BaseModel):
    action: str = Field(..., pattern="^(add|list|complete|delete|update)$")
    title: Optional[str] = None
    description: Optional[str] = None
    priority: int = Field(default=1, ge=1, le=5)
    due_date: Optional[str] = None
    category: Optional[str] = None
    todo_id: Optional[str] = None
    status: str = "pending"


class EmailRequest(BaseModel):
    action: str = Field(..., pattern="^(send|query)$")
    to: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    is_html: bool = False


class SearchToolRequest(BaseModel):
    query: str
    source: str = Field(default="both", pattern="^(web|knowledge|both)$")
    top_k: int = Field(default=5, ge=1, le=20)


def _tools(db: AsyncSession, current: CurrentUser) -> ToolService:
    return ToolService(db, current.tenant_id)


@router.get("/list", response_model=APIResponse)
async def list_tools(
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    return success_response(data=await _tools(db, current).list_tools())


@router.post("/execute", response_model=APIResponse)
async def execute_tool(
    request: ToolExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    service = _tools(db, current)
    result = await service.execute(request.tool_name, request.params)
    if result["success"]:
        return success_response(data=result)
    return json_error_response(
        500, "工具执行失败", result.get("error"), http_status=500
    )


@router.post("/calendar", response_model=APIResponse)
async def call_calendar(
    request: CalendarRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    service = _tools(db, current)
    result = await service.execute("calendar", request.model_dump(exclude_none=True))
    if result["success"]:
        return success_response(data=result)
    return json_error_response(500, "日历工具失败", result.get("error"), http_status=500)


@router.post("/todo", response_model=APIResponse)
async def call_todo(
    request: TodoRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    service = _tools(db, current)
    result = await service.execute("todo", request.model_dump(exclude_none=True))
    if result["success"]:
        return success_response(data=result)
    return json_error_response(500, "待办工具失败", result.get("error"), http_status=500)


@router.post("/email", response_model=APIResponse)
async def call_email(
    request: EmailRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    service = _tools(db, current)
    result = await service.execute("email", request.model_dump(exclude_none=True))
    if result["success"]:
        return success_response(data=result)
    return json_error_response(500, "邮件工具失败", result.get("error"), http_status=500)


@router.post("/search", response_model=APIResponse)
async def call_search(
    request: SearchToolRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    service = _tools(db, current)
    result = await service.execute(
        "search",
        {"query": request.query, "source": request.source, "top_k": request.top_k},
    )
    if result["success"]:
        return success_response(data=result)
    return json_error_response(500, "搜索失败", result.get("error"), http_status=500)
