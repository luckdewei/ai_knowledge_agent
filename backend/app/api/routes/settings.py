"""API Key 与运行时配置（覆盖 .env）。"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.runtime_settings import (
    API_KEY_FIELDS,
    list_settings_for_api,
    update_settings,
)
from app.models.response import APIResponse, success_response

router = APIRouter()


class UpdateApiKeysRequest(BaseModel):
    """仅提交需要修改的字段；空字符串表示清除页面配置并回退 .env。"""

    deepseek_api_key: Optional[str] = Field(default=None)
    embedding_api_key: Optional[str] = Field(default=None)
    speech_api_key: Optional[str] = Field(default=None)
    tavily_api_key: Optional[str] = Field(default=None)
    smtp_username: Optional[str] = Field(default=None)
    smtp_password: Optional[str] = Field(default=None)


@router.get("/keys", response_model=APIResponse)
async def get_api_keys():
    """获取各 API Key 配置状态（掩码展示，不返回明文）。"""
    return success_response(
        data={
            "fields": list_settings_for_api(),
            "hint": "页面留空并保存表示清除覆盖；未在页面配置时自动使用 backend/.env",
        }
    )


@router.put("/keys", response_model=APIResponse)
async def put_api_keys(body: UpdateApiKeysRequest):
    """保存 API Key 到运行时配置并立即生效。"""
    updates = body.model_dump(exclude_unset=True)
    fields = update_settings(updates)
    return success_response(
        data={
            "fields": fields,
            "message": "配置已保存并生效",
        }
    )


@router.get("/keys/schema", response_model=APIResponse)
async def get_keys_schema():
    """字段说明（不含密钥值）。"""
    return success_response(data={"fields": API_KEY_FIELDS})
