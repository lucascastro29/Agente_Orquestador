from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router as api_router
from app.db.models import Base
from app.db.session import engine
from app.telegram.webhook import router as telegram_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crear tablas si no existen (desarrollo — en producción usar Alembic)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Agente Orquestador", lifespan=lifespan)

app.include_router(api_router)
app.include_router(telegram_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
