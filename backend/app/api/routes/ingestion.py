from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser, get_current_user
from app.models.response import APIResponse, success_response
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


def _svc(db: AsyncSession, current: CurrentUser) -> IngestionService:
    return IngestionService(db, current.tenant_id)


@router.post("/ingest", response_model=APIResponse[IngestResponse])
async def ingest_content(
    request: IngestRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    return success_response(data=await _svc(db, current).ingest(request))


@router.post("/file", response_model=APIResponse[IngestResponse])
async def upload_file(
    file: UploadFile = File(...),
    auto_tag: bool = Form(True),
    auto_summarize: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    content = await file.read()
    request = IngestRequest(
        source_type=SourceType.FILE,
        content=content,
        file_path=file.filename,
        auto_tag=auto_tag,
        auto_summarize=auto_summarize,
    )
    return success_response(data=await _svc(db, current).ingest(request))


@router.post("/url", response_model=APIResponse[IngestResponse])
async def ingest_url(
    body: UrlIngestRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    request = IngestRequest(
        source_type=SourceType.URL,
        content=str(body.url),
        url=body.url,
        auto_tag=body.auto_tag,
        auto_summarize=body.auto_summarize,
        fetch_metadata=body.fetch_metadata,
    )
    return success_response(data=await _svc(db, current).ingest(request))


@router.post("/clipboard", response_model=APIResponse[IngestResponse])
async def ingest_clipboard(
    body: ClipboardIngestRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    request = IngestRequest(
        source_type=SourceType.CLIPBOARD,
        content=body.content,
        auto_tag=body.auto_tag,
        auto_summarize=False,
    )
    return success_response(data=await _svc(db, current).ingest(request))


@router.post("/voice", response_model=APIResponse[IngestResponse])
async def ingest_voice(
    body: VoiceIngestRequest,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
):
    request = IngestRequest(
        source_type=SourceType.VOICE,
        content=body.audio_base64,
        auto_tag=True,
        auto_summarize=False,
        voice_format=body.voice_format,
        voice_duration=body.duration,
        request_metadata={"duration": body.duration} if body.duration else None,
    )
    return success_response(data=await _svc(db, current).ingest(request))
