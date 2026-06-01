import httpx
from typing import Tuple, Optional
from urllib.parse import urlparse
from datetime import datetime
import logging

from bs4 import BeautifulSoup
from readability import Document as ReadabilityDocument
import trafilatura

from app.models.ingestion import ContentMetadata

logger = logging.getLogger(__name__)


class URLExtractor:
    """网页内容提取器"""

    def __init__(self):
        self.timeout = 30.0
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    async def extract(
        self, url: str, fetch_metadata: bool = True
    ) -> Tuple[str, ContentMetadata]:
        """
        提取网页内容

        Args:
            url: 网页 URL
            fetch_metadata: 是否提取元数据（标题、作者等）
        """
        # 1. 获取 HTML 内容
        html_content = await self._fetch_html(url)

        # 2. 提取主要内容
        content = await self._extract_main_content(html_content, url)

        # 3. 提取元数据
        metadata = (
            await self._extract_metadata(html_content, url)
            if fetch_metadata
            else ContentMetadata(
                original_source=url,
                title=urlparse(url).netloc,
            )
        )

        metadata.original_source = url
        metadata.extracted_from = "url_extractor"
        metadata.word_count = len(content.split())

        return content, metadata

    async def _fetch_html(self, url: str) -> str:
        """获取 HTML 内容"""
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

            # 检测编码
            if response.encoding:
                return response.text
            else:
                # 尝试从 content-type 或 HTML meta 检测
                return response.text

    async def _extract_main_content(self, html: str, url: str) -> str:
        """提取网页主要内容（多重策略）"""

        # 策略1: 使用 readability (提取文章主体)
        try:
            doc = ReadabilityDocument(html)
            content = doc.summary()
            # 清理 HTML 标签
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            if len(text) > 200:  # 有效内容
                return text
        except Exception as e:
            logger.debug(f"Readability extraction failed: {e}")

        # 策略2: 使用 trafilatura (专门的内容提取)
        try:
            text = trafilatura.extract(html, include_links=False, include_tables=True)
            if text and len(text) > 200:
                return text
        except Exception as e:
            logger.debug(f"Trafilatura extraction failed: {e}")

        # 策略3: 回退到 BeautifulSoup 提取正文区域
        soup = BeautifulSoup(html, "html.parser")

        # 移除脚本和样式
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # 查找常见正文容器
        content_selectors = [
            "article",
            "main",
            ".post-content",
            ".article-content",
            ".content",
            "#content",
            ".entry-content",
            ".post-body",
        ]

        main_content = None
        for selector in content_selectors:
            elem = soup.select_one(selector)
            if elem:
                main_content = elem
                break

        if main_content:
            text = main_content.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return text

        # 最终回退：返回整个页面文本（过滤后）
        text = soup.get_text(separator="\n", strip=True)
        # 清理多余空行
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return "\n".join(lines)

    async def _extract_metadata(self, html: str, url: str) -> ContentMetadata:
        """提取网页元数据"""
        soup = BeautifulSoup(html, "html.parser")

        # 提取标题
        title = None
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # 提取描述
        description = None
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            description = str(meta_desc["content"])

        # 提取作者
        author = None
        meta_author = soup.find("meta", attrs={"name": "author"})
        if meta_author and meta_author.get("content"):
            author = str(meta_author["content"])

        # 提取发布时间
        published_time = None
        meta_date = soup.find("meta", attrs={"property": "article:published_time"})
        if meta_date and meta_date.get("content"):
            try:
                published_time = datetime.fromisoformat(
                    str(meta_date["content"]).replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # 域名作为来源标识
        domain = urlparse(url).netloc

        return ContentMetadata(
            original_source=url,
            title=title or domain,
            author=author,
            created_at=published_time,
            extra_metadata={
                "description": description,
                "domain": domain,
                "url": url,
            },
            extracted_from="url_extractor",
        )
