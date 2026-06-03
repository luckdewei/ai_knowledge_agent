import time
import logging
from typing import List, Optional

from app.core.ingestion.extractors.file_extractor import FileExtractor
from app.core.ingestion.extractors.url_extractor import URLExtractor
from app.core.ingestion.extractors.clipboard_extractor import ClipboardExtractor
from app.core.ingestion.extractors.voice_extractor import VoiceExtractor
from app.services.knowledge_service import KnowledgeService
from app.models.ingestion import IngestRequest, IngestResponse, SourceType, ContentMetadata
from app.models.schemas import KnowledgeCreate

from app.core.ingestion.markdown_format import format_stored_content

logger = logging.getLogger(__name__)


class IngestionService:
    """统一摄取服务"""

    def __init__(self, db_session, tenant_id):
        self.db = db_session
        self.knowledge_service = KnowledgeService(db_session, tenant_id)
        self.file_extractor = FileExtractor(enable_ocr=False)
        self.url_extractor = URLExtractor()
        self.clipboard_extractor = ClipboardExtractor()
        self.voice_extractor = VoiceExtractor()

    async def ingest(self, request: IngestRequest) -> IngestResponse:
        """统一摄取入口"""
        start_time = time.time()

        try:
            content, metadata = await self._route_extractor(request)
            content = format_stored_content(
                content,
                source_type=request.source_type.value,
                page_title=metadata.title,
            )

            content_hash = self.knowledge_service.compute_content_hash(content)

            # 同 URL 重新抓取：更新已有条目（而非仅提示重复）
            if request.source_type == SourceType.URL:
                refreshed = await self._refresh_existing_url(
                    request, content, content_hash, metadata, start_time
                )
                if refreshed is not None:
                    return refreshed

            existing = await self.knowledge_service.get_by_hash(content_hash)
            if existing:
                logger.info(f"Duplicate content detected: {content_hash[:8]}")
                return IngestResponse(
                    success=True,
                    knowledge_id=str(existing.id),
                    title=existing.title,
                    content_preview=content[:200],
                    content_hash=content_hash,
                    source_type=request.source_type,
                    is_duplicate=True,
                    processing_time_ms=(time.time() - start_time) * 1000,
                )

            auto_tags: List[str] = []
            if request.auto_tag:
                auto_tags = await self._auto_tag_content(content)

            auto_summary = None
            if request.auto_summarize:
                auto_summary = await self._auto_summarize(content)

            knowledge_in = self._build_knowledge_create(
                request, content, content_hash, metadata, auto_tags, auto_summary
            )

            knowledge = await self.knowledge_service.create(knowledge_in)

            processing_time = (time.time() - start_time) * 1000
            logger.info(f"Ingested {request.source_type.value}: {knowledge.title[:50]}")

            return IngestResponse(
                success=True,
                knowledge_id=str(knowledge.id),
                title=knowledge.title,
                content_preview=content[:200],
                content_hash=content_hash,
                source_type=request.source_type,
                auto_tags=auto_tags,
                auto_summary=auto_summary,
                processing_time_ms=processing_time,
                is_duplicate=False,
                is_updated=False,
            )

        except Exception as e:
            logger.error(f"Ingestion failed: {e}", exc_info=True)
            return IngestResponse(
                success=False,
                title="",
                content_preview="",
                content_hash="",
                source_type=request.source_type,
                processing_time_ms=(time.time() - start_time) * 1000,
                error=str(e),
            )

    async def _refresh_existing_url(
        self,
        request: IngestRequest,
        content: str,
        content_hash: str,
        metadata: ContentMetadata,
        start_time: float,
    ) -> Optional[IngestResponse]:
        url = request.get_url()
        existing = await self.knowledge_service.get_by_source_uri(url)
        if not existing:
            return None

        auto_tags: List[str] = list(existing.tags or [])
        if request.auto_tag:
            auto_tags = await self._auto_tag_content(content)

        auto_summary = None
        if request.auto_summarize:
            auto_summary = await self._auto_summarize(content)

        title = metadata.title or self._generate_title(content)
        extra = self._build_metadata(metadata, request, auto_summary)

        knowledge = await self.knowledge_service.replace_from_ingestion(
            str(existing.id),
            title=title,
            content=content,
            content_hash=content_hash,
            tags=auto_tags if auto_tags else None,
            metadata=extra,
        )
        if not knowledge:
            return None

        return IngestResponse(
            success=True,
            knowledge_id=str(knowledge.id),
            title=knowledge.title,
            content_preview=content[:200],
            content_hash=content_hash,
            source_type=request.source_type,
            auto_tags=auto_tags,
            auto_summary=auto_summary,
            processing_time_ms=(time.time() - start_time) * 1000,
            is_duplicate=False,
            is_updated=True,
        )

    def _build_metadata(
        self,
        metadata: ContentMetadata,
        request: IngestRequest,
        auto_summary: Optional[str],
    ) -> dict:
        try:
            processing = metadata.model_dump(mode="json")
        except Exception:
            processing = {"original_source": metadata.original_source}
        return {
            **metadata.extra_dict(),
            **(request.request_metadata or {}),
            "auto_summary": auto_summary,
            "processing_metadata": processing,
        }

    def _build_knowledge_create(
        self,
        request: IngestRequest,
        content: str,
        content_hash: str,
        metadata: ContentMetadata,
        auto_tags: List[str],
        auto_summary: Optional[str],
    ) -> KnowledgeCreate:
        return KnowledgeCreate(
            title=metadata.title or self._generate_title(content),
            content=content,
            content_hash=content_hash,
            source_type=request.source_type.value,
            source_uri=metadata.original_source,
            tags=auto_tags if auto_tags else None,
            metadata=self._build_metadata(metadata, request, auto_summary),
        )

    async def _route_extractor(self, request: IngestRequest):
        """路由到对应的提取器"""
        if request.source_type == SourceType.FILE:
            return await self.file_extractor.extract(
                request.get_file_path(), request.file_type
            )

        elif request.source_type == SourceType.URL:
            return await self.url_extractor.extract(
                request.get_url(), request.fetch_metadata
            )

        elif request.source_type == SourceType.CLIPBOARD:
            return await self.clipboard_extractor.extract(request.get_text_content())

        elif request.source_type == SourceType.VOICE:
            return await self.voice_extractor.extract_from_base64(
                request.get_voice_base64(),
                format=request.voice_format,
                duration=request.voice_duration,
            )

        else:
            raise ValueError(f"Unsupported source type: {request.source_type}")

    async def _auto_tag_content(self, content: str) -> List[str]:
        prompt = f"""
        从以下文本中提取 3-5 个最相关的关键词作为标签。
        只返回关键词列表，用逗号分隔，不要有其他内容。

        文本: {content[:1000]}

        关键词:
        """
        try:
            from app.core.agent.llm import get_llm

            llm = get_llm()
            response = await llm.ainvoke(prompt)
            tags = [tag.strip() for tag in response.content.split(",") if tag.strip()]
            return tags[:5]
        except Exception as e:
            logger.warning(f"Auto-tagging failed: {e}")
            return []

    async def _auto_summarize(self, content: str) -> Optional[str]:
        if len(content) < 100:
            return None

        prompt = f"""
        请为以下文本生成一个简短的摘要（2-3句话，100字以内）。

        文本: {content[:2000]}

        摘要:
        """
        try:
            from app.core.agent.llm import get_llm

            llm = get_llm()
            response = await llm.ainvoke(prompt)
            return response.content.strip()
        except Exception as e:
            logger.warning(f"Auto-summarization failed: {e}")
            return None

    def _generate_title(self, content: str, max_length: int = 80) -> str:
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        if lines:
            first = lines[0].lstrip("#").strip()
            if first and len(first) <= max_length:
                return first
        if len(content) > max_length:
            return content[:max_length].strip() + "..."
        return content[:max_length].strip() or "未命名笔记"
