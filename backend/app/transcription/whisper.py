"""Transcripción de audio — usa OpenAI Whisper API si hay key, sino faster-whisper local."""
import asyncio
import logging
import os
import tempfile
from functools import lru_cache

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
_PROMPT_ES = "Transcripción en español rioplatense uruguayo. Usar 'vos' en lugar de 'tú'."

_MIME: dict[str, str] = {
    "ogg":  "audio/ogg",
    "oga":  "audio/ogg",
    "mp3":  "audio/mpeg",
    "mp4":  "audio/mp4",
    "m4a":  "audio/mp4",
    "wav":  "audio/wav",
    "webm": "audio/webm",
    "flac": "audio/flac",
}


def _mime_for(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "ogg"
    return _MIME.get(ext, "audio/ogg")


@lru_cache(maxsize=1)
def _get_local_model():
    """Carga el modelo faster-whisper una sola vez y lo cachea en memoria."""
    from faster_whisper import WhisperModel
    model_name = settings.whisper_model or "base"
    logger.info("Cargando modelo faster-whisper '%s' (primera vez puede tardar)…", model_name)
    return WhisperModel(model_name, device="cpu", compute_type="int8")


def _transcribe_local_sync(audio_bytes: bytes, filename: str) -> str:
    ext = ("." + filename.rsplit(".", 1)[-1]) if "." in filename else ".ogg"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name
    try:
        model = _get_local_model()
        segments, _ = model.transcribe(
            tmp_path,
            language="es",
            initial_prompt=_PROMPT_ES,
            vad_filter=True,  # elimina silencios
        )
        return "".join(s.text for s in segments).strip()
    finally:
        os.unlink(tmp_path)


async def transcribe(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    """Transcribe audio en español.

    Prioridad:
    1. OpenAI Whisper API (si OPENAI_API_KEY está configurado)
    2. faster-whisper local (modelo configurado en WHISPER_MODEL, default 'base')
    """
    if settings.openai_api_key:
        return await _transcribe_openai(audio_bytes, filename)
    return await _transcribe_local(audio_bytes, filename)


async def _transcribe_openai(audio_bytes: bytes, filename: str) -> str:
    mime = _mime_for(filename)
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            _WHISPER_URL,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            files={"file": (filename, audio_bytes, mime)},
            data={"model": "whisper-1", "language": "es", "prompt": _PROMPT_ES},
        )
        resp.raise_for_status()
        text: str = resp.json().get("text", "").strip()
    logger.info("Transcripción OpenAI completada: %d chars", len(text))
    return text


async def _transcribe_local(audio_bytes: bytes, filename: str) -> str:
    # Corre en thread pool para no bloquear el event loop
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, _transcribe_local_sync, audio_bytes, filename)
    logger.info("Transcripción local completada: %d chars", len(text))
    return text
