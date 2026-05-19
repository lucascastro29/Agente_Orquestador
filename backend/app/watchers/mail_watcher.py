"""Watcher de Gmail — clasifica mails nuevos con Haiku y notifica al orquestador."""
import asyncio
import json
import logging
from datetime import datetime, timezone

import anthropic
import httpx

from app.config import settings
from app.worker import celery_app

logger = logging.getLogger(__name__)

_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

_CLASSIFIER_SYSTEM = """
Sos un filtro de relevancia de emails. Respondé SOLO con JSON:
{"relevant": true/false, "reason": "una frase corta"}

Un email es relevante si:
- Requiere acción del usuario en las próximas 24h
- Es de un contacto importante (cliente, jefe, socio)
- Contiene información urgente o crítica
- Es una factura, contrato o documento importante

NO es relevante si:
- Es newsletter, marketing, notificación automática
- Es spam o promoción
- Es una confirmación genérica sin acción requerida
"""


def _gmail_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.gmail_oauth_token}",
        "Content-Type": "application/json",
    }


async def _get_or_create_watcher_state(watcher: str) -> tuple[str, str | None]:
    """Devuelve (watcher_id, last_history_id)."""
    from app.db.session import AsyncSessionLocal
    from app.db.models import WatcherState
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WatcherState).where(WatcherState.watcher == watcher))
        state = result.scalar_one_or_none()
        if not state:
            state = WatcherState(watcher=watcher)
            db.add(state)
            await db.commit()
            await db.refresh(state)
        return state.id, state.last_history_id


async def _save_history_id(watcher: str, history_id: str) -> None:
    from app.db.session import AsyncSessionLocal
    from app.db.models import WatcherState
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WatcherState).where(WatcherState.watcher == watcher))
        state = result.scalar_one_or_none()
        if state:
            state.last_history_id = history_id
            state.last_checked_at = datetime.now(timezone.utc)
            await db.commit()


async def _get_new_message_ids(last_history_id: str | None) -> list[str]:
    """Devuelve IDs de mensajes nuevos en INBOX."""
    async with httpx.AsyncClient(timeout=15) as client:
        if last_history_id:
            # Fetch incremental por historyId
            resp = await client.get(
                f"{_GMAIL_BASE}/history",
                headers=_gmail_headers(),
                params={
                    "startHistoryId": last_history_id,
                    "historyTypes": "messageAdded",
                    "labelId": "INBOX",
                },
            )
            if resp.status_code == 404:
                # historyId vencido — hacer full fetch
                last_history_id = None
            else:
                resp.raise_for_status()
                history = resp.json()
                ids = []
                for record in history.get("history", []):
                    for added in record.get("messagesAdded", []):
                        ids.append(added["message"]["id"])
                return ids

        # Full fetch: últimos 10 mensajes no leídos del INBOX
        label_filter = " ".join(f"label:{lbl}" for lbl in settings.gmail_watched_labels)
        resp = await client.get(
            f"{_GMAIL_BASE}/messages",
            headers=_gmail_headers(),
            params={"q": f"is:unread {label_filter}", "maxResults": 10},
        )
        resp.raise_for_status()
        messages = resp.json().get("messages", [])
        return [m["id"] for m in messages]


async def _get_message_data(msg_id: str) -> dict | None:
    """Recupera from, subject y snippet de un mensaje."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{_GMAIL_BASE}/messages/{msg_id}",
            headers=_gmail_headers(),
            params={"format": "metadata", "metadataHeaders": ["From", "Subject"]},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()

    headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
    return {
        "id": msg_id,
        "from": headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "snippet": data.get("snippet", ""),
        "history_id": data.get("historyId"),
    }


async def _classify_mail(mail: dict) -> bool:
    """Usa Haiku para decidir si el mail es relevante."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    prompt = (
        f"De: {mail['from']}\n"
        f"Asunto: {mail['subject']}\n"
        f"Extracto: {mail['snippet'][:300]}"
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
        logger.warning("Clasificación de mail falló: %s", exc)
        return False


async def _notify_for_mail(mail: dict) -> None:
    """Corre el orquestador con el evento de mail y envía la respuesta a Telegram."""
    from app.db.session import AsyncSessionLocal
    from app.agents.runner import AgentRunner

    async with AsyncSessionLocal() as db:
        runner = AgentRunner(db)
        text = await runner.receive_watcher_event("mail", mail)

    if text and settings.telegram_allowed_chat_id:
        from app.telegram.client import send_message
        await send_message(settings.telegram_allowed_chat_id, text)


async def _check_mail_async() -> None:
    if not settings.gmail_oauth_token:
        logger.debug("gmail_oauth_token no configurado — watcher deshabilitado")
        return
    if not settings.gmail_watcher_enabled:
        logger.debug("gmail_watcher_enabled=False — watcher deshabilitado")
        return

    _, last_history_id = await _get_or_create_watcher_state("mail")

    try:
        msg_ids = await _get_new_message_ids(last_history_id)
    except Exception as exc:
        logger.error("Error obteniendo mensajes de Gmail: %s", exc)
        return

    latest_history_id = last_history_id
    for msg_id in msg_ids:
        try:
            mail = await _get_message_data(msg_id)
            if not mail:
                continue
            if mail.get("history_id"):
                latest_history_id = mail["history_id"]
            relevant = await _classify_mail(mail)
            if relevant:
                await _notify_for_mail(mail)
        except Exception as exc:
            logger.error("Error procesando mail %s: %s", msg_id, exc)

    if latest_history_id and latest_history_id != last_history_id:
        await _save_history_id("mail", latest_history_id)


@celery_app.task(name="watchers.check_mail")
def check_mail() -> None:
    asyncio.run(_check_mail_async())
