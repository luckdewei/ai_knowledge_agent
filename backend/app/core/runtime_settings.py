"""
运行时 API 配置：页面保存的密钥覆盖 .env，未设置则回退环境变量。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# backend/data/runtime_settings.json
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_SETTINGS_FILE = _DATA_DIR / "runtime_settings.json"

SourceType = Literal["env", "runtime", "none"]

# 可在设置页配置并覆盖 .env 的字段
API_KEY_FIELDS: list[dict[str, str]] = [
    {
        "key": "deepseek_api_key",
        "env_var": "DEEPSEEK_API_KEY",
        "label": "DeepSeek API Key",
        "description": "Agent 对话与推理（platform.deepseek.com）",
        "group": "大模型",
    },
    {
        "key": "embedding_api_key",
        "env_var": "EMBEDDING_API_KEY",
        "label": "Embedding API Key",
        "description": "知识库向量检索（如硅基流动）",
        "group": "向量模型",
    },
    {
        "key": "speech_api_key",
        "env_var": "SPEECH_API_KEY",
        "label": "语音识别 API Key",
        "description": "语音摄取；留空则复用 Embedding Key",
        "group": "向量模型",
    },
    {
        "key": "tavily_api_key",
        "env_var": "TAVILY_API_KEY",
        "label": "Tavily API Key",
        "description": "Agent 联网搜索（tavily.com）",
        "group": "搜索",
    },
    {
        "key": "smtp_username",
        "env_var": "SMTP_USERNAME",
        "label": "SMTP 用户名",
        "description": "邮件工具发信账号",
        "group": "邮件",
    },
    {
        "key": "smtp_password",
        "env_var": "SMTP_PASSWORD",
        "label": "SMTP 密码",
        "description": "邮件工具发信密码 / 授权码",
        "group": "邮件",
    },
]

_FIELD_KEYS = {f["key"] for f in API_KEY_FIELDS}


def _env_snapshot() -> dict[str, Any]:
    """启动时 .env 中的原始值（用于回退与展示是否已配置）。"""
    snap: dict[str, Any] = {}
    for field in API_KEY_FIELDS:
        key = field["key"]
        val = getattr(settings, key, None)
        if isinstance(val, str):
            snap[key] = val.strip()
        elif val is not None:
            snap[key] = val
        else:
            snap[key] = ""
    return snap


_ENV_VALUES: dict[str, Any] = _env_snapshot()
_RUNTIME_OVERRIDES: dict[str, str] = {}


def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_file() -> dict[str, str]:
    if not _SETTINGS_FILE.is_file():
        return {}
    try:
        raw = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {
            k: str(v).strip()
            for k, v in raw.items()
            if k in _FIELD_KEYS and v is not None and str(v).strip()
        }
    except Exception as e:
        logger.warning("Failed to load runtime settings: %s", e)
        return {}


def _save_file(overrides: dict[str, str]) -> None:
    _ensure_data_dir()
    _SETTINGS_FILE.write_text(
        json.dumps(overrides, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"


def apply_runtime_to_settings() -> None:
    """将运行时覆盖合并进全局 settings（空覆盖则用 .env 快照）。"""
    global _RUNTIME_OVERRIDES
    _RUNTIME_OVERRIDES = _load_file()
    for field in API_KEY_FIELDS:
        key = field["key"]
        override = _RUNTIME_OVERRIDES.get(key, "")
        env_val = _ENV_VALUES.get(key, "")
        if isinstance(env_val, str):
            env_val = env_val.strip()
        effective = override if override else env_val
        setattr(settings, key, effective)
    logger.debug(
        "Runtime settings applied, overrides: %s",
        list(_RUNTIME_OVERRIDES.keys()),
    )


def get_field_meta(key: str) -> dict[str, str]:
    for f in API_KEY_FIELDS:
        if f["key"] == key:
            return f
    raise KeyError(key)


def _resolve_source(key: str) -> SourceType:
    override = _RUNTIME_OVERRIDES.get(key, "")
    env_val = (_ENV_VALUES.get(key) or "").strip() if isinstance(
        _ENV_VALUES.get(key), str
    ) else _ENV_VALUES.get(key)
    if override:
        return "runtime"
    if env_val:
        return "env"
    return "none"


def list_settings_for_api() -> list[dict[str, Any]]:
    """供前端展示：掩码值 + 来源 + 是否已配置。"""
    items: list[dict[str, Any]] = []
    for field in API_KEY_FIELDS:
        key = field["key"]
        override = _RUNTIME_OVERRIDES.get(key, "")
        env_val = _ENV_VALUES.get(key, "")
        if isinstance(env_val, str):
            env_val = env_val.strip()
        effective = override or env_val or ""
        source = _resolve_source(key)
        items.append(
            {
                "key": key,
                "env_var": field["env_var"],
                "label": field["label"],
                "description": field["description"],
                "group": field["group"],
                "masked_value": mask_secret(effective) if effective else "",
                "source": source,
                "configured": bool(effective),
                "env_configured": bool(env_val),
                "runtime_configured": bool(override),
            }
        )
    return items


def update_settings(updates: dict[str, Optional[str]]) -> list[dict[str, Any]]:
    """
    更新运行时覆盖。
    - 值为 None：不修改该项
    - 值为 \"\"：清除该项运行时覆盖，回退 .env
    - 非空字符串：写入运行时覆盖
    """
    global _RUNTIME_OVERRIDES
    current = dict(_RUNTIME_OVERRIDES)
    for key, value in updates.items():
        if key not in _FIELD_KEYS:
            continue
        if value is None:
            continue
        trimmed = value.strip()
        if trimmed:
            current[key] = trimmed
        else:
            current.pop(key, None)
    _save_file(current)
    apply_runtime_to_settings()
    return list_settings_for_api()


def init_runtime_settings() -> None:
    """应用启动时调用。"""
    apply_runtime_to_settings()
