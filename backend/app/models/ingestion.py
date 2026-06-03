"""统一数据模型"""

import base64

from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from typing import Optional, List, Dict, Any, Union
from enum import Enum
from datetime import datetime


class SourceType(str, Enum):
    """来源类型枚举"""

    FILE = "file"
    URL = "url"
    CLIPBOARD = "clipboard"
    VOICE = "voice"
    WECHAT = "wechat"
    EMAIL = "email"


class FileType(str, Enum):
    """文件类型枚举"""

    MARKDOWN = "md"
    PDF = "pdf"
    TXT = "txt"
    DOCX = "docx"
    HTML = "html"
    JSON = "json"
    CSV = "csv"
    IMAGE = "image"  # 需要 OCR


class ContentMetadata(BaseModel):
    """内容元数据"""

    model_config = ConfigDict(from_attributes=True)

    original_source: str  # 原始来源标识
    title: Optional[str] = None
    author: Optional[str] = None
    word_count: Optional[int] = None
    language: Optional[str] = None  # zh-CN, en-US
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    extracted_from: Optional[str] = None  # 提取方式
    confidence: Optional[float] = None  # 提取置信度
    extra_metadata: Optional[Dict[str, Any]] = None  # 扩展元数据（如 description、domain）

    def extra_dict(self) -> Dict[str, Any]:
        """返回扩展元数据字典，便于合并进知识条目的 metadata 字段。"""
        return dict(self.extra_metadata or {})


class IngestRequest(BaseModel):
    """统一摄取请求"""

    source_type: SourceType
    content: Union[str, bytes, HttpUrl]  # 具体内容、路径或 Base64 音频
    auto_tag: bool = True  # 自动生成标签
    auto_summarize: bool = False  # 自动生成摘要（可选）
    request_metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="请求级附加元数据"
    )

    # 文件特定字段
    file_path: Optional[str] = None
    file_type: Optional[FileType] = None

    # URL 特定字段
    url: Optional[HttpUrl] = None
    fetch_metadata: bool = True

    # 语音特定字段
    voice_duration: Optional[float] = None
    voice_format: str = "webm"
    speaker_count: Optional[int] = 1

    def get_file_path(self) -> str:
        """解析文件路径（FILE 来源）。"""
        if self.file_path:
            return self.file_path
        if isinstance(self.content, str):
            return self.content
        if isinstance(self.content, bytes):
            return self.content.decode("utf-8")
        raise ValueError("file source requires file_path or string content")

    def get_url(self) -> str:
        """解析 URL（URL 来源）。"""
        if self.url is not None:
            return str(self.url)
        if isinstance(self.content, HttpUrl):
            return str(self.content)
        if isinstance(self.content, str):
            return self.content
        raise ValueError("url source requires url or string content")

    def get_text_content(self) -> str:
        """解析文本内容（CLIPBOARD 来源）。"""
        if isinstance(self.content, str):
            return self.content
        if isinstance(self.content, bytes):
            return self.content.decode("utf-8")
        raise ValueError("clipboard source requires string or bytes content")

    def get_voice_base64(self) -> str:
        """解析 Base64 音频（VOICE 来源）。"""
        if isinstance(self.content, str):
            return self.content
        if isinstance(self.content, bytes):
            return base64.b64encode(self.content).decode("ascii")
        raise ValueError("voice source requires string or bytes content")


class UrlIngestRequest(BaseModel):
    """URL 摄取请求"""

    url: HttpUrl
    auto_tag: bool = True
    auto_summarize: bool = False
    fetch_metadata: bool = True


class ClipboardIngestRequest(BaseModel):
    """剪贴板摄取请求"""

    content: str
    auto_tag: bool = True


class VoiceIngestRequest(BaseModel):
    """语音摄取请求"""

    audio_base64: str
    duration: Optional[float] = None
    voice_format: str = "webm"


class IngestResponse(BaseModel):
    """摄取响应"""

    success: bool
    knowledge_id: Optional[str] = None
    title: str
    content_preview: str
    content_hash: str
    source_type: SourceType
    auto_tags: List[str] = []
    auto_summary: Optional[str] = None
    processing_time_ms: float
    is_duplicate: bool = False
    is_updated: bool = False
    error: Optional[str] = None
