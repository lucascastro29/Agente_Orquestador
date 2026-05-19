"""Transcripción de audio via OpenAI Whisper API."""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"

# Tipos MIME por extensión
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


async def transcribe(audio_bytes: bytes, filename: str = "audio.ogg") -> str:
    """Transcribe audio en español usando Whisper-1.

    Raises:
        RuntimeError: si OPENAI_API_KEY no está configurado.
        httpx.HTTPStatusError: si la API devuelve error.
    """
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY no configurado — la transcripción de voz no está disponible."
        )

    mime = _mime_for(filename)
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            _WHISPER_URL,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            files={"file": (filename, audio_bytes, mime)},
            data={
                "model": "whisper-1",
                "language": "es",          # español
                "prompt": (                # hint para acento uruguayo/rioplatense
                    "Transcripción en español rioplatense uruguayo. "
                    "Usar 'vos' en lugar de 'tú'."
                ),
            },
        )
        resp.raise_for_status()
        text: str = resp.json().get("text", "").strip()

    logger.info("Transcripción completada: %d chars", len(text))
    return text
