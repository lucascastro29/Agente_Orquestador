"""Watcher de Google Calendar — detecta eventos próximos y notifica al orquestador."""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import anthropic
import httpx

from app.config import settings
from app.worker import celery_app

logger = logging.getLogger(__name__)

_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"

_CLASSIFIER_SYSTEM = """
Sos un filtro de relevancia para eventos de calendario. Respondé SOLO con JSON:
{"relevant": true/false, "reason": "una frase corta"}

Un evento es relevante (vale notificar) si:
- Empieza en menos de 60 minutos
- Tiene asistentes externos (fuera de tu dominio)
- Tiene palabras clave: reunión, demo, cliente, entrevista, deadline, vencimiento
- El título sugiere algo importante o con preparación previa necesaria

NO es relevante si:
- Es un evento recurrente de rutina sin asistentes (ej: "Almuerzo")
- Ya está en curso
- Es un bloque de tiempo genérico (ej: "Focus time", "Deep work")
"""


def _calendar_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.calendar_oauth_token}",
        "Content-Type": "application/json",
    }


async def _get_upcoming_events() -> list[dict]:
    """Obtiene eventos del calendario primario en las próximas 2 horas."""
    now = datetime.now(timezone.utc)
    time_max = now + timedelta(hours=2)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{_CALENDAR_BASE}/calendars/primary/events",
            headers=_calendar_headers(),
            params={
                "timeMin": now.isoformat(),
                "timeMax": time_max.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 10,
            },
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])

    events = []
    for item in items:
        start = item.get("start", {})
        start_time = start.get("dateTime") or start.get("date", "")
        attendees = [
            a.get("email", "") for a in item.get("attendees", [])
            if not a.get("self", False)
        ]
        events.append({
            "id": item["id"],
            "title": item.get("summary", "(sin título)"),
            "time": start_time,
            "attendees": ", ".join(attendees) if attendees else "",
            "description": (item.get("description") or "")[:200],
        })
    return events


async def _get_notified_ids() -> set[str]:
    """Devuelve IDs de eventos ya notificados hoy (guardados en WatcherState.extra)."""
    from app.db.session import AsyncSessionLocal
    from app.db.models import WatcherState
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WatcherState).where(WatcherState.watcher == "calendar")
        )
        state = result.scalar_one_or_none()
        if not state:
            state = WatcherState(watcher="calendar")
            db.add(state)
            await db.commit()
            await db.refresh(state)
        extra = state.extra or {}
        # Limpiar IDs del día anterior
        today = datetime.now(timezone.utc).date().isoformat()
        if extra.get("date") != today:
            return set()
        return set(extra.get("notified_ids", []))


async def _save_notified_id(event_id: str) -> None:
    from app.db.session import AsyncSessionLocal
    from app.db.models import WatcherState
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WatcherState).where(WatcherState.watcher == "calendar")
        )
        state = result.scalar_one_or_none()
        if not state:
            return
        today = datetime.now(timezone.utc).date().isoformat()
        extra = state.extra or {}
        if extra.get("date") != today:
            extra = {"date": today, "notified_ids": []}
        existing = extra.get("notified_ids", [])
        if event_id not in existing:
            existing.append(event_id)
        extra["notified_ids"] = existing
        state.extra = extra
        state.last_checked_at = datetime.now(timezone.utc)
        await db.commit()


async def _classify_event(event: dict) -> bool:
    """Usa Haiku para decidir si el evento merece notificación."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    prompt = (
        f"Título: {event['title']}\n"
        f"Hora: {event['time']}\n"
        f"Asistentes: {event['attendees'] or 'ninguno'}\n"
        f"Descripción: {event['description'] or 'ninguna'}"
    )
    try:
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=64,
            system=_CLASSIFIER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        data = json.loads(text)
        return bool(data.get("relevant", False))
    except Exception as exc:
        logger.warning("Clasificación de evento falló: %s", exc)
        return False


async def _notify_for_event(event: dict) -> None:
    """Corre el orquestador con el evento de calendario y envía la respuesta a Telegram."""
    from app.db.session import AsyncSessionLocal
    from app.agents.runner import AgentRunner

    async with AsyncSessionLocal() as db:
        runner = AgentRunner(db)
        text = await runner.receive_watcher_event("calendar", event)

    if text and settings.telegram_allowed_chat_id:
        from app.telegram.client import send_message
        await send_message(settings.telegram_allowed_chat_id, text)


async def _check_calendar_async() -> None:
    if not settings.calendar_oauth_token:
        logger.debug("calendar_oauth_token no configurado — watcher deshabilitado")
        return
    if not settings.calendar_watcher_enabled:
        logger.debug("calendar_watcher_enabled=False — watcher deshabilitado")
        return

    try:
        events = await _get_upcoming_events()
    except Exception as exc:
        logger.error("Error obteniendo eventos de Calendar: %s", exc)
        return

    notified = await _get_notified_ids()

    for event in events:
        if event["id"] in notified:
            continue
        try:
            relevant = await _classify_event(event)
            if relevant:
                await _notify_for_event(event)
                await _save_notified_id(event["id"])
        except Exception as exc:
            logger.error("Error procesando evento %s: %s", event["id"], exc)


@celery_app.task(name="watchers.check_calendar")
def check_calendar() -> None:
    asyncio.run(_check_calendar_async())
