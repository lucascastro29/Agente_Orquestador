from dataclasses import dataclass
from datetime import date, timezone, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Message, Session as DBSession

# Precios en USD por millón de tokens
# Incluye alias cortos y IDs completos que devuelve la API
PRICES: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6":            {"input": 3.0, "output": 15.0, "cache_read": 0.3,  "cache_write": 3.75},
    "claude-haiku-4-5":             {"input": 1.0, "output":  5.0, "cache_read": 0.1,  "cache_write": 1.25},
    "claude-haiku-4-5-20251001":    {"input": 1.0, "output":  5.0, "cache_read": 0.1,  "cache_write": 1.25},
    "claude-opus-4-7":              {"input": 5.0, "output": 25.0, "cache_read": 0.5,  "cache_write": 6.25},
}

_FALLBACK = {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75}


def _normalize_model(model: str) -> str:
    """Devuelve el precio del modelo aunque la API devuelva el ID con fecha."""
    if model in PRICES:
        return model
    # Intentar prefijo: "claude-haiku-4-5-20251001" → buscar "claude-haiku-4-5"
    for key in PRICES:
        if model.startswith(key):
            return key
    return model


@dataclass
class LimitResult:
    ok: bool
    reason: str = ""


class CostTracker:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def calculate(self, model: str, usage: object) -> float:
        p = PRICES.get(_normalize_model(model), _FALLBACK)
        total = 0.0
        total += getattr(usage, "input_tokens", 0) * p["input"] / 1_000_000
        total += getattr(usage, "output_tokens", 0) * p["output"] / 1_000_000
        total += getattr(usage, "cache_read_input_tokens", 0) * p["cache_read"] / 1_000_000
        total += getattr(usage, "cache_creation_input_tokens", 0) * p["cache_write"] / 1_000_000
        return total

    def format_footer_telegram(
        self, turn_cost: float, session_cost: float, usage: object
    ) -> str:
        in_tok = getattr(usage, "input_tokens", 0)
        out_tok = getattr(usage, "output_tokens", 0)
        cache_r = getattr(usage, "cache_read_input_tokens", 0)
        return (
            f"\n\n<tg-spoiler>💰 turno ${turn_cost:.5f} | sesión ${session_cost:.4f} "
            f"| in {in_tok} out {out_tok} cache↩{cache_r}</tg-spoiler>"
        )

    def format_footer_web(
        self, turn_cost: float, session_cost: float, usage: object
    ) -> dict:
        return {
            "turn_cost_usd": turn_cost,
            "session_cost_usd": session_cost,
            "input_tokens": getattr(usage, "input_tokens", 0),
            "output_tokens": getattr(usage, "output_tokens", 0),
            "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0),
            "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0),
        }

    async def check_limits(
        self, session_id: str, turn_cost: float, max_session: float, max_day: float
    ) -> LimitResult:
        # Costo acumulado de la sesión
        result = await self.db.execute(
            select(DBSession.total_cost_usd).where(DBSession.id == session_id)
        )
        session_cost = (result.scalar_one_or_none() or 0.0) + turn_cost
        if session_cost > max_session:
            return LimitResult(ok=False, reason=f"Límite de sesión alcanzado (${session_cost:.4f} > ${max_session})")

        # Costo del día
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        day_result = await self.db.execute(
            select(func.sum(Message.cost_usd)).where(Message.created_at >= today_start)
        )
        day_cost = (day_result.scalar_one_or_none() or 0.0) + turn_cost
        if day_cost > max_day:
            return LimitResult(ok=False, reason=f"Límite diario alcanzado (${day_cost:.4f} > ${max_day})")

        return LimitResult(ok=True)
