import asyncio
import io
import logging
import re
import subprocess
import wave
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

VOICE_DIR = Path("/app/piper_voices")
VOICE_NAME = "es_ES-davefx-medium"
_HF_BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
    "/es/es_ES/davefx/medium"
)

_CLEAN_RE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\*{1,3}([^*\n]+)\*{1,3}"), r"\1"),
    (re.compile(r"#{1,6}\s+"), ""),
    (re.compile(r"`{1,3}[^`]*`{1,3}", re.DOTALL), ""),
    # Eliminar footer de costo (empieza con ─ o con la línea del separador)
    (re.compile(r"─.*", re.DOTALL), ""),
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),
    (re.compile(r"^\s*[-*+]\s+", re.MULTILINE), ""),
    (re.compile(r"<[^>]+>"), ""),
]

MAX_CHARS = 3000


class TTSService:
    def __init__(self) -> None:
        self._voice: object | None = None
        self._lock = asyncio.Lock()
        self._available: bool | None = None  # None = sin verificar

    async def _ensure_model(self) -> None:
        async with self._lock:
            if self._voice is not None:
                return
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_model)

    def _load_model(self) -> None:
        try:
            from piper import PiperVoice  # type: ignore[import]
        except ImportError:
            self._available = False
            logger.warning("piper-tts no instalado — TTS desactivado")
            raise

        model_path = VOICE_DIR / f"{VOICE_NAME}.onnx"
        config_path = VOICE_DIR / f"{VOICE_NAME}.onnx.json"

        if not model_path.exists() or not config_path.exists():
            self._download_model()

        self._voice = PiperVoice.load(
            str(model_path),
            config_path=str(config_path),
            use_cuda=False,
        )
        self._available = True
        logger.info("Piper TTS listo: %s", VOICE_NAME)

    def _download_model(self) -> None:
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=180, follow_redirects=True) as client:
            for ext in (".onnx", ".onnx.json"):
                dest = VOICE_DIR / f"{VOICE_NAME}{ext}"
                if dest.exists():
                    continue
                url = f"{_HF_BASE}/{VOICE_NAME}{ext}"
                logger.info("Descargando modelo TTS: %s", url)
                r = client.get(url)
                r.raise_for_status()
                dest.write_bytes(r.content)

    async def synthesize_wav(self, text: str) -> bytes:
        """Devuelve bytes WAV del texto. Limpia markdown y footers antes."""
        cleaned = _clean_text(text[:MAX_CHARS])
        if not cleaned.strip():
            return b""
        try:
            await self._ensure_model()
        except Exception:
            return b""

        loop = asyncio.get_event_loop()

        def _gen() -> bytes:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                self._voice.synthesize(cleaned, wf)  # type: ignore[union-attr]
            return buf.getvalue()

        return await loop.run_in_executor(None, _gen)

    async def synthesize_ogg(self, text: str) -> bytes:
        """Devuelve bytes OGG Opus (para Telegram voice)."""
        wav = await self.synthesize_wav(text)
        if not wav:
            return b""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _wav_to_ogg, wav)


def _clean_text(text: str) -> str:
    for pattern, repl in _CLEAN_RE:
        text = pattern.sub(repl, text)
    return text.strip()


def _wav_to_ogg(wav_bytes: bytes) -> bytes:
    proc = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", "pipe:0",
            "-c:a", "libopus",
            "-b:a", "48k",
            "-f", "ogg",
            "pipe:1",
        ],
        input=wav_bytes,
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg: {proc.stderr.decode()[:200]}")
    return proc.stdout


tts_service = TTSService()
