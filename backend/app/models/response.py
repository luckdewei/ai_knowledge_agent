"""统一 API 响应模型"""

from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from fastapi.responses import JSONResponse

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """统一 API 响应"""

    success: bool = True
    code: int = 200
    message: str = "success"
    data: Optional[T] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ErrorResponse(BaseModel):
    """错误响应"""

    success: bool = False
    code: int
    message: str
    detail: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class PageResponse(BaseModel, Generic[T]):
    """分页响应"""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def success_response(data: Any = None, message: str = "success") -> APIResponse:
    """成功响应工厂函数"""
    return APIResponse(success=True, code=200, message=message, data=data)


def error_response(
    code: int, message: str, detail: Optional[str] = None
) -> ErrorResponse:
    """错误响应工厂函数"""
    return ErrorResponse(success=False, code=code, message=message, detail=detail)


def json_error_response(
    code: int,
    message: str,
    detail: Optional[str] = None,
    *,
    http_status: Optional[int] = None,
) -> JSONResponse:
    """错误 JSON 响应（用于路由直接返回）"""
    return JSONResponse(
        status_code=http_status if http_status is not None else code,
        content=error_response(code, message, detail).model_dump(),
    )
