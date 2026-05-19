from fastapi import FastAPI

app = FastAPI(title="Agente Orquestador")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
