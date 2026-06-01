from app.core.ingestion.extractors.voice_extractor import _parse_audio_base64


def test_parse_audio_base64():
    audio_base64 = "data:audio/webm;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA="
    audio_bytes, format = _parse_audio_base64(audio_base64, "webm")
    assert audio_bytes is not None
    assert format == "webm"
    assert len(audio_bytes) > 0
    assert isinstance(audio_bytes, bytes)
    assert isinstance(format, str)
    assert format in ["webm", "mp3", "wav", "m4a", "ogg", "flac"]
    assert len(audio_bytes) > 0
    assert isinstance(audio_bytes, bytes)
    assert isinstance(format, str)
    assert format in ["webm", "mp3", "wav", "m4a", "ogg", "flac"]
