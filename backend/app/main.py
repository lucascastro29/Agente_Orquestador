import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.db.models import Base
from app.db.session import engine
from app.telegram.webhook import router as telegram_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Pre-cargar modelo TTS en background (primer síntesis es lenta por la descarga)
    async def _preload_tts() -> None:
        try:
            from app.tts.service import tts_service
            await tts_service._ensure_model()
        except Exception:
            pass  # TTS es opcional — no bloquear el arranque

    asyncio.create_task(_preload_tts())

    # Iniciar polling de Telegram en background (no requiere webhook ni ngrok)
    from app.telegram.polling import run_polling
    polling_task = asyncio.create_task(run_polling())

    yield

    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Agente Orquestador", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(telegram_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
