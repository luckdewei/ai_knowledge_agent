import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import aiofiles
import markdown
import pytesseract
from bs4 import BeautifulSoup
from docx import Document
from PIL import Image
from pypdf import PdfReader

from app.models.ingestion import FileType, ContentMetadata

logger = logging.getLogger(__name__)


class FileExtractor:
    """文件内容提取器"""

    # 最大文件大小限制 (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024

    def __init__(self, enable_ocr: bool = False):
        self.enable_ocr = enable_ocr

    async def extract(
        self, file_path: str, file_type: Optional[FileType] = None
    ) -> Tuple[str, ContentMetadata]:
        """
        提取文件内容

        Args:
            file_path: 文件路径
            file_type: 文件类型（自动检测如果未提供）

        Returns:
            (content, metadata)
        """
        path = Path(file_path)

        # 检查文件是否存在
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # 检查文件大小
        file_size = path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            raise ValueError(
                f"File too large: {file_size} bytes (max {self.MAX_FILE_SIZE})"
            )

        # 确定文件类型
        if file_type is None:
            from app.core.ingestion.detector import ContentTypeDetector

            file_type = ContentTypeDetector.detect_file_type(file_path) or FileType.TXT

        resolved_type = file_type

        # 提取内容
        if resolved_type == FileType.PDF:
            content, meta = await self._extract_pdf(path)
        elif resolved_type == FileType.DOCX:
            content, meta = await self._extract_docx(path)
        elif resolved_type == FileType.MARKDOWN:
            content, meta = await self._extract_markdown(path)
        elif resolved_type == FileType.TXT:
            content, meta = await self._extract_text(path)
        elif resolved_type == FileType.JSON:
            content, meta = await self._extract_json(path)
        elif resolved_type == FileType.IMAGE and self.enable_ocr:
            content, meta = await self._extract_image_ocr(path)
        else:
            # 默认按文本处理
            content, meta = await self._extract_text(path)

        # 补充元数据
        meta.original_source = str(path.absolute())
        meta.file_size = file_size
        meta.extracted_from = f"file_extractor_{resolved_type.value}"

        return content, meta

    async def _extract_text(self, path: Path) -> Tuple[str, ContentMetadata]:
        """提取纯文本文件"""
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()

        metadata = ContentMetadata(
            original_source=str(path),
            title=path.stem,
            word_count=len(content.split()),
            language=self._detect_language(content),
            modified_at=datetime.fromtimestamp(path.stat().st_mtime),
        )

        return content, metadata

    async def _extract_markdown(self, path: Path) -> Tuple[str, ContentMetadata]:
        """提取 Markdown 文件"""
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            md_content = await f.read()

        # 转换为纯文本（移除 Markdown 语法）
        html = markdown.markdown(md_content)
        soup = BeautifulSoup(html, "html.parser")
        content = soup.get_text(separator="\n")

        metadata = ContentMetadata(
            original_source=str(path),
            title=path.stem,
            word_count=len(content.split()),
            language=self._detect_language(content),
            modified_at=datetime.fromtimestamp(path.stat().st_mtime),
        )

        return content, metadata

    async def _extract_pdf(self, path: Path) -> Tuple[str, ContentMetadata]:
        """提取 PDF 文件（同步但在线程池中执行）"""

        def sync_extract():
            reader = PdfReader(str(path))
            text_pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_pages.append(text)
            return "\n".join(text_pages)

        # 在线程池中运行（因为 PyPDF2 是同步的）
        content = await asyncio.to_thread(sync_extract)

        metadata = ContentMetadata(
            original_source=str(path),
            title=path.stem,
            word_count=len(content.split()),
            language=self._detect_language(content),
            modified_at=datetime.fromtimestamp(path.stat().st_mtime),
            mime_type="application/pdf",
        )

        return content, metadata

    async def _extract_docx(self, path: Path) -> Tuple[str, ContentMetadata]:
        """提取 Word 文档"""

        def sync_extract():
            doc = Document(str(path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)

        content = await asyncio.to_thread(sync_extract)

        metadata = ContentMetadata(
            original_source=str(path),
            title=path.stem,
            word_count=len(content.split()),
            language=self._detect_language(content),
            modified_at=datetime.fromtimestamp(path.stat().st_mtime),
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        return content, metadata

    async def _extract_json(self, path: Path) -> Tuple[str, ContentMetadata]:
        """提取 JSON 文件"""
        import json

        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()

        # 格式化 JSON 以便阅读
        try:
            data = json.loads(content)
            content = json.dumps(data, ensure_ascii=False, indent=2)
        except:
            pass  # 保持原样

        metadata = ContentMetadata(
            original_source=str(path),
            title=path.stem,
            word_count=len(content.split()),
            language=self._detect_language(content),
            modified_at=datetime.fromtimestamp(path.stat().st_mtime),
        )

        return content, metadata

    async def _extract_image_ocr(self, path: Path) -> Tuple[str, ContentMetadata]:
        """使用 OCR 提取图片中的文字"""
        if not self.enable_ocr:
            raise ValueError("OCR not enabled")

        def sync_ocr():
            image = Image.open(path)
            text = pytesseract.image_to_string(image, lang="chi_sim+eng")
            return text

        content = await asyncio.to_thread(sync_ocr)

        metadata = ContentMetadata(
            original_source=str(path),
            title=path.stem,
            word_count=len(content.split()),
            language="mixed",
            modified_at=datetime.fromtimestamp(path.stat().st_mtime),
            confidence=0.8,  # OCR 置信度估计
        )

        return content, metadata

    def _detect_language(self, text: str) -> str:
        """简单语言检测"""
        # 统计中文字符比例
        chinese_chars = len([c for c in text if "\u4e00" <= c <= "\u9fff"])
        total_chars = len([c for c in text if c.isalpha()])

        if total_chars == 0:
            return "unknown"

        chinese_ratio = chinese_chars / total_chars
        if chinese_ratio > 0.3:
            return "zh-CN"
        else:
            return "en-US"
