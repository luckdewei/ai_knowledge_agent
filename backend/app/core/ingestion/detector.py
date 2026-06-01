import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from app.models.ingestion import SourceType, FileType


class ContentTypeDetector:
    """内容类型识别器"""

    # URL 正则表达式
    URL_PATTERN = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # 可选端口
        r"(?:/?|[/?]\S+)$",  #
        re.IGNORECASE,  # 忽略大小写
    )

    # 常见文件扩展名
    TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".rst", ".text"}
    DOC_EXTENSIONS = {".pdf", ".docx", ".doc", ".odt"}
    CODE_EXTENSIONS = {".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c"}
    DATA_EXTENSIONS = {".json", ".csv", ".xml", ".yaml", ".yml"}
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

    @classmethod
    def detect_source_type(cls, input_str: str) -> Tuple[SourceType, Optional[str]]:
        """
        检测输入内容类型

        Returns:
            (SourceType, 具体标识)
        """
        # 检测是否为 URL
        if cls.is_url(input_str):
            return SourceType.URL, input_str

        # 检测是否为文件路径
        if cls.is_file_path(input_str):
            return SourceType.FILE, input_str

        # 默认为文本内容（剪贴板）
        return SourceType.CLIPBOARD, None

    @classmethod
    def is_url(cls, text: str) -> bool:
        """判断是否为 URL"""
        return bool(cls.URL_PATTERN.match(text.strip()))

    @classmethod
    def is_file_path(cls, path: str) -> bool:
        """判断是否为文件路径"""
        # 简单判断：包含文件扩展名且不以 http 开头
        if path.startswith(("http://", "https://")):
            return False

        # 检查是否有扩展名
        has_extension = any(
            path.lower().endswith(ext)
            for ext in cls.TEXT_EXTENSIONS
            | cls.DOC_EXTENSIONS
            | cls.CODE_EXTENSIONS
            | cls.DATA_EXTENSIONS
            | cls.IMAGE_EXTENSIONS
        )

        return has_extension

    @classmethod
    def detect_file_type(cls, file_path: str) -> Optional[FileType]:
        """根据扩展名检测文件类型"""
        lower_path = file_path.lower()

        for ext in cls.TEXT_EXTENSIONS:
            if lower_path.endswith(ext):
                return (
                    FileType.MARKDOWN if ext in {".md", ".markdown"} else FileType.TXT
                )

        for ext in cls.DOC_EXTENSIONS:
            if lower_path.endswith(ext):
                if ext == ".pdf":
                    return FileType.PDF
                elif ext == ".docx":
                    return FileType.DOCX

        for ext in cls.DATA_EXTENSIONS:
            if lower_path.endswith(ext):
                if ext == ".json":
                    return FileType.JSON
                elif ext == ".csv":
                    return FileType.CSV

        for ext in cls.IMAGE_EXTENSIONS:
            if lower_path.endswith(ext):
                return FileType.IMAGE

        return FileType.TXT  # 默认
