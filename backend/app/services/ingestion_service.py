import time
import asyncio
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor
import logging

from app.core.ingestion.detector import ContentTypeDetector
from app.core.ingestion.extractors.file_extractor import FileExtractor
from app.core.ingestion.extractors.url_extractor import URLExtractor
from app.core.ingestion.extractors.clipboard_extractor import ClipboardExtractor
from app.core.ingestion.extractors.voice_extractor import VoiceExtractor
from app.services.knowledge_service import KnowledgeService
from app.models.ingestion import IngestRequest, IngestResponse, SourceType
from app.models.schemas import KnowledgeCreate
from app.core.vector.embeddings import embeddings_service

logger = logging.getLogger(__name__)


class IngestionService:
    """统一摄取服务"""

    def __init__(self, db_session):
        self.db = db_session
        self.knowledge_service = KnowledgeService(db_session)
        self.file_extractor = FileExtractor(enable_ocr=False)
        self.url_extractor = URLExtractor()
        self.clipboard_extractor = ClipboardExtractor()
        self.voice_extractor = VoiceExtractor()

        # 线程池用于同步操作
        self.thread_pool = ThreadPoolExecutor(max_workers=4)

    async def ingest(self, request: IngestRequest) -> IngestResponse:
        """统一摄取入口"""
        start_time = time.time()

        try:
            # 1. 路由到对应的提取器
            content, metadata = await self._route_extractor(request)

            # 2. 计算内容哈希并去重
            content_hash = self.knowledge_service.compute_content_hash(content)
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

            # 3. 自动生成标签（如果需要）
            auto_tags = []
            if request.auto_tag:
                auto_tags = await self._auto_tag_content(content)

            # 4. 自动生成摘要（如果需要）
            auto_summary = None
            if request.auto_summarize:
                auto_summary = await self._auto_summarize(content)

            # 5. 创建知识条目
            knowledge_in = KnowledgeCreate(
                title=metadata.title or self._generate_title(content),
                content=content,
                content_hash=content_hash,
                source_type=request.source_type.value,
                source_uri=metadata.original_source,
                tags=auto_tags if auto_tags else None,
                metadata={
                    **metadata.extra_dict(),
                    **(request.request_metadata or {}),
                    "auto_summary": auto_summary,
                    "processing_metadata": metadata.model_dump(mode="json"),
                },
            )

            knowledge = await self.knowledge_service.create(knowledge_in)

            # 6. 后处理（异步，不阻塞响应）
            if auto_summary or auto_tags:
                asyncio.create_task(
                    self._post_process(str(knowledge.id), auto_tags, auto_summary)
                )

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
        """自动生成标签"""
        # 使用 LLM 提取关键词
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
            return tags[:5]  # 最多5个标签
        except Exception as e:
            logger.warning(f"Auto-tagging failed: {e}")
            return []

    async def _auto_summarize(self, content: str) -> Optional[str]:
        """自动生成摘要"""
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

    async def _post_process(
        self, knowledge_id: str, tags: List[str], summary: Optional[str]
    ):
        """异步后处理"""
        try:
            # 更新知识条目（添加摘要和标签）
            from app.models.schemas import KnowledgeUpdate

            metadata = {}
            if summary:
                metadata["auto_summary"] = summary

            update_data = KnowledgeUpdate(
                tags=tags,
                metadata=metadata if metadata else None,
            )

            await self.knowledge_service.update(knowledge_id, update_data)
            logger.debug(f"Post-processing completed for {knowledge_id}")
        except Exception as e:
            logger.error(f"Post-processing failed: {e}")

    def _generate_title(self, content: str, max_length: int = 80) -> str:
        """生成标题"""
        # 取第一行非空内容
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        if lines:
            first_line = lines[0]
            if len(first_line) <= max_length:
                return first_line

        # 取前 max_length 字符
        if len(content) > max_length:
            return content[:max_length].strip() + "..."

        return content[:max_length].strip() or "未命名笔记"
