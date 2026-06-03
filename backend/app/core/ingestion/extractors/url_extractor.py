import httpx
from typing import Tuple
from urllib.parse import urlparse
from datetime import datetime
import logging
import re

from bs4 import BeautifulSoup

from app.models.ingestion import ContentMetadata
from app.core.ingestion.markdown_format import (
    extract_markdown_from_html,
    ensure_document_title,
    polish_extracted_markdown,
)

logger = logging.getLogger(__name__)

_CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class URLExtractor:
    """网页内容提取器（输出 Markdown）"""

    def __init__(self):
        self.timeout = 30.0

    async def extract(
        self, url: str, fetch_metadata: bool = True
    ) -> Tuple[str, ContentMetadata]:
        html_content = await self._fetch_html(url)
        metadata = (
            await self._extract_metadata(html_content, url)
            if fetch_metadata
            else ContentMetadata(
                original_source=url,
                title=urlparse(url).netloc,
            )
        )

        content = extract_markdown_from_html(html_content, url=url)
        title = metadata.title or urlparse(url).netloc
        content = ensure_document_title(content, title)

        metadata.original_source = url
        metadata.extracted_from = "url_extractor"
        metadata.word_count = len(content.split())

        return content, metadata

    async def _fetch_html(self, url: str) -> str:
        headers = {
            "User-Agent": _CHROME_UA,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            text = response.text
            if not text or len(text) < 50:
                raw = response.content
                enc = response.charset_encoding or "utf-8"
                try:
                    text = raw.decode(enc, errors="replace")
                except LookupError:
                    text = raw.decode("utf-8", errors="replace")
            return text

    def _pick_title(self, soup: BeautifulSoup, url: str) -> str:
        candidates: list[str] = []

        for prop in ("og:title", "twitter:title", "article:title"):
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                candidates.append(str(tag["content"]).strip())

        h1 = soup.find("h1")
        if h1:
            t = h1.get_text(strip=True)
            if t:
                candidates.append(t)

        if soup.title and soup.title.string:
            candidates.append(soup.title.string.strip())

        domain = urlparse(url).netloc
        for raw in candidates:
            t = re.sub(r"\s+", " ", raw).strip()
            if not t or len(t) < 2:
                continue
            # 去掉常见站点后缀「 - 知乎」「 | 新浪」
            t = re.split(r"\s*[-|_]\s*", t)[0].strip() or t
            if t.lower() in ("home", "index", domain):
                continue
            return t[:200]

        return domain

    async def _extract_metadata(self, html: str, url: str) -> ContentMetadata:
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")
        title = self._pick_title(soup, url)

        description = None
        for attrs in (
            {"name": "description"},
            {"property": "og:description"},
        ):
            meta_desc = soup.find("meta", attrs=attrs)
            if meta_desc and meta_desc.get("content"):
                description = str(meta_desc["content"]).strip()
                break

        author = None
        meta_author = soup.find("meta", attrs={"name": "author"})
        if meta_author and meta_author.get("content"):
            author = str(meta_author["content"])

        published_time = None
        for attrs in (
            {"property": "article:published_time"},
            {"name": "pubdate"},
            {"name": "publishdate"},
        ):
            meta_date = soup.find("meta", attrs=attrs)
            if meta_date and meta_date.get("content"):
                try:
                    published_time = datetime.fromisoformat(
                        str(meta_date["content"]).replace("Z", "+00:00")
                    )
                    break
                except ValueError:
                    pass

        domain = urlparse(url).netloc

        return ContentMetadata(
            original_source=url,
            title=title,
            author=author,
            created_at=published_time,
            extra_metadata={
                "description": description,
                "domain": domain,
                "url": url,
            },
            extracted_from="url_extractor",
        )
