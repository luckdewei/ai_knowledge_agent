from typing import Tuple
import re
import logging

from app.models.ingestion import ContentMetadata

logger = logging.getLogger(__name__)


class ClipboardExtractor:
    """剪贴板内容提取器"""

    def __init__(self, max_length: int = 10000):
        self.max_length = max_length

    async def extract(self, content: str) -> Tuple[str, ContentMetadata]:
        """
        处理剪贴板内容

        Args:
            content: 剪贴板原始文本
        """
        if not content:
            raise ValueError("Empty clipboard content")

        # 1. 清理内容
        cleaned_content = self._clean_content(content)

        # 2. 限制长度
        if len(cleaned_content) > self.max_length:
            logger.warning(
                f"Clipboard content truncated from {len(cleaned_content)} to {self.max_length} chars"
            )
            cleaned_content = cleaned_content[: self.max_length]

        # 3. 生成标题（使用第一行或前50个字符）
        title = self._generate_title(cleaned_content)

        # 4. 检测内容类型
        content_type = self._detect_content_type(content)

        metadata = ContentMetadata(
            original_source="clipboard",
            title=title,
            word_count=len(cleaned_content.split()),
            language=self._detect_language(cleaned_content),
            extra_metadata={
                "content_type": content_type,
                "original_length": len(content),
                "truncated": len(content) > self.max_length,
            },
            extracted_from="clipboard_extractor",
        )

        return cleaned_content, metadata

    def _clean_content(self, content: str) -> str:
        """清理内容"""
        # 移除多余空格
        content = re.sub(r" +", " ", content)
        # 规范化换行
        content = re.sub(r"\n\s*\n", "\n\n", content)
        # 移除行首行尾空格
        lines = [line.strip() for line in content.split("\n")]
        return "\n".join(lines).strip()

    def _generate_title(self, content: str, max_length: int = 80) -> str:
        """生成标题"""
        # 取第一行
        first_line = content.split("\n")[0].strip()
        if first_line and len(first_line) < max_length:
            return first_line

        # 取前 max_length 个字符
        if len(content) > max_length:
            return content[:max_length].strip() + "..."

        return content[:max_length].strip()

    def _detect_content_type(self, content: str) -> str:
        """检测内容类型"""
        # JSON
        if content.strip().startswith(("{", "[")) and content.count("{") > 0:
            try:
                import json

                json.loads(content)
                return "json"
            except:
                pass

        # 代码
        code_indicators = [
            "def ",
            "class ",
            "import ",
            "function(",
            "=>",
            "public class",
        ]
        if any(indicator in content for indicator in code_indicators):
            return "code"

        # 列表
        if re.search(r"^\s*[-*•]\s", content, re.MULTILINE):
            return "list"

        # 普通文本
        return "text"

    def _detect_language(self, text: str) -> str:
        """简单语言检测"""
        chinese_chars = len([c for c in text if "\u4e00" <= c <= "\u9fff"])
        english_chars = len([c for c in text if c.isalpha() and c < "\u4e00"])

        if chinese_chars > english_chars:
            return "zh-CN"
        else:
            return "en-US"
