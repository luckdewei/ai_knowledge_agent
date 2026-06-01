import base64
from typing import Tuple, Optional
import logging
from pathlib import Path

import httpx

from app.models.ingestion import ContentMetadata
from app.core.config import settings

logger = logging.getLogger(__name__)

_AUDIO_MIME = {
    "webm": "audio/webm",
    "mp3": "audio/mpeg",
    "mpeg": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
}

_MIME_TO_FORMAT = {
    "audio/webm": "webm",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/wav": "wav",
    "audio/ogg": "ogg",
    "audio/flac": "flac",
}


def _parse_audio_base64(audio_base64: str, format: str) -> tuple[bytes, str]:
    """解析 Base64 音频，兼容 `data:audio/...;base64,...` Data URI。"""
    payload = audio_base64.strip()
    inferred_format = format

    if payload.startswith("data:"):
        header, _, encoded = payload.partition(",")
        if not encoded:
            raise ValueError("Invalid data URI: missing base64 payload")

        payload = encoded
        mime_type = header[5:].split(";", 1)[0].lower()
        if format == "webm":
            inferred_format = _MIME_TO_FORMAT.get(mime_type, format)

    audio_bytes = base64.b64decode(payload, validate=False)
    if not audio_bytes:
        raise ValueError("Empty audio data after base64 decode")

    return audio_bytes, inferred_format


class VoiceExtractor:
    """语音转文字提取器（硅基流动 SenseVoice / TeleSpeech）"""

    def __init__(self):
        self.api_key = settings.speech_api_key or settings.embedding_api_key
        self.api_url = settings.speech_base_url
        self.model = settings.speech_model

        if not self.api_key:
            logger.warning(
                "SPEECH_API_KEY / EMBEDDING_API_KEY not set, voice transcription will fail!"
            )

    async def extract_from_base64(
        self, audio_base64: str, format: str = "webm", duration: Optional[float] = None
    ) -> Tuple[str, ContentMetadata]:
        """
        从 Base64 编码的音频提取文字

        Args:
            audio_base64: Base64 编码的音频数据
            format: 音频格式 (webm, mp3, wav, m4a)
            duration: 音频时长（秒）
        """
        audio_bytes, format = _parse_audio_base64(audio_base64, format)
        return await self._transcribe(audio_bytes, format, duration)

    async def extract_from_file(
        self, file_path: str, duration: Optional[float] = None
    ) -> Tuple[str, ContentMetadata]:
        """从音频文件提取文字"""
        with open(file_path, "rb") as f:
            audio_bytes = f.read()

        format = Path(file_path).suffix.lstrip(".")
        return await self._transcribe(audio_bytes, format, duration)

    async def _transcribe(
        self, audio_bytes: bytes, format: str, duration: Optional[float] = None
    ) -> Tuple[str, ContentMetadata]:
        """转录音频"""
        text = await self._transcribe_with_siliconflow(audio_bytes, format)

        title = text.split("\n")[0][:50] if text else "语音笔记"
        if len(title) < 5:
            title = "语音笔记"

        metadata = ContentMetadata(
            original_source="voice",
            title=title,
            word_count=len(text.split()),
            language="zh-CN",
            extra_metadata={
                "audio_format": format,
                "duration_seconds": duration,
                "asr_model": self.model,
                "asr_provider": "siliconflow",
            },
            extracted_from="voice_extractor",
            confidence=0.9,
        )

        return text, metadata

    async def _transcribe_with_siliconflow(
        self, audio_bytes: bytes, format: str
    ) -> str:
        """使用硅基流动语音识别 API 转录音频"""
        if not self.api_key:
            raise RuntimeError(
                "Speech API key not configured. Set SPEECH_API_KEY or EMBEDDING_API_KEY."
            )

        mime = _AUDIO_MIME.get(format.lower(), f"audio/{format}")
        filename = f"audio.{format}"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (filename, audio_bytes, mime)},
                data={"model": self.model},
            )
            if response.is_error:
                logger.error(
                    "SiliconFlow ASR failed: status=%s body=%s",
                    response.status_code,
                    response.text[:500],
                )
                raise RuntimeError(
                    f"Speech transcription failed ({response.status_code}): "
                    f"{response.text[:200]}"
                )

            data = response.json()
            return data.get("text", "").strip()
