from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.ingestion_service import IngestionService
from app.models.ingestion import (
    IngestRequest,
    IngestResponse,
    SourceType,
    UrlIngestRequest,
    ClipboardIngestRequest,
    VoiceIngestRequest,
)

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse)
async def ingest_content(request: IngestRequest, db: AsyncSession = Depends(get_db)):
    """统一摄取接口"""
    service = IngestionService(db)
    return await service.ingest(request)


@router.post("/file")
async def upload_file(
    file: UploadFile = File(...),
    auto_tag: bool = Form(True),
    auto_summarize: bool = Form(False),
    db: AsyncSession = Depends(get_db),
):
    """上传文件并摄取"""
    content = await file.read()

    request = IngestRequest(
        source_type=SourceType.FILE,
        content=content,
        file_path=file.filename,
        auto_tag=auto_tag,
        auto_summarize=auto_summarize,
    )

    service = IngestionService(db)
    return await service.ingest(request)


@router.post("/url", response_model=IngestResponse)
async def ingest_url(
    body: UrlIngestRequest, db: AsyncSession = Depends(get_db)
):
    """摄取网页 URL"""
    url = str(body.url)
    request = IngestRequest(
        source_type=SourceType.URL,
        content=url,
        url=body.url,
        auto_tag=body.auto_tag,
        auto_summarize=body.auto_summarize,
        fetch_metadata=body.fetch_metadata,
    )

    service = IngestionService(db)
    return await service.ingest(request)


@router.post("/clipboard", response_model=IngestResponse)
async def ingest_clipboard(
    body: ClipboardIngestRequest, db: AsyncSession = Depends(get_db)
):
    """摄取剪贴板内容"""
    request = IngestRequest(
        source_type=SourceType.CLIPBOARD,
        content=body.content,
        auto_tag=body.auto_tag,
        auto_summarize=False,
    )

    service = IngestionService(db)
    return await service.ingest(request)


@router.post("/voice", response_model=IngestResponse)
async def ingest_voice(
    body: VoiceIngestRequest, db: AsyncSession = Depends(get_db)
):
    """摄取语音笔记（Base64 编码）"""
    request = IngestRequest(
        source_type=SourceType.VOICE,
        content=body.audio_base64,
        auto_tag=True,
        auto_summarize=False,
        voice_format=body.voice_format,
        voice_duration=body.duration,
        request_metadata={"duration": body.duration} if body.duration else None,
    )

    service = IngestionService(db)
    return await service.ingest(request)
