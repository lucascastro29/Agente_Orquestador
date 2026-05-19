"""Polling mode — alternativa a webhook, no requiere URL pública."""
import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot"
_offset: int = 0


async def _get_updates(timeout: int = 30) -> list[dict]:
    global _offset
    url = f"{_BASE}{settings.telegram_bot_token}/getUpdates"
    params = {"timeout": timeout, "offset": _offset, "allowed_updates": ["message", "callback_query"]}
    async with httpx.AsyncClient(timeout=timeout + 5) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    updates = data.get("result", [])
    if updates:
        _offset = updates[-1]["update_id"] + 1
    return updates


async def _delete_webhook() -> None:
    """Elimina cualquier webhook activo para poder usar polling."""
    url = f"{_BASE}{settings.telegram_bot_token}/deleteWebhook"
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json={"drop_pending_updates": False})


async def run_polling() -> None:
    """Loop de polling — se inicia en el lifespan de FastAPI."""
    if not settings.telegram_bot_token:
        logger.info("TELEGRAM_BOT_TOKEN no configurado — polling desactivado")
        return

    await _delete_webhook()
    logger.info("Telegram polling activo")

    # Importación aquí para evitar ciclos
    from app.telegram.webhook import _handle_callback, _get_or_create_telegram_session, _load_prior_messages, _split_message
    from app.agents.runner import AgentRunner
    from app.security.validator import SecurityValidator
    from app.telegram.client import send_message, send_with_approval, send_security_alert
    from app.db.models import PendingApproval
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import select

    while True:
        try:
            updates = await _get_updates(timeout=30)
        except Exception as exc:
            logger.warning("Error en getUpdates: %s", exc)
            await asyncio.sleep(5)
            continue

        for update in updates:
            try:
                async with AsyncSessionLocal() as db:
                    if "callback_query" in update:
                        await _handle_callback(update["callback_query"], db)
                        continue

                    message = update.get("message", {})
                    chat_id = str(message.get("chat", {}).get("id", ""))
                    text = message.get("text", "").strip()

                    if not chat_id or not text:
                        continue

                    if settings.telegram_allowed_chat_id and chat_id != settings.telegram_allowed_chat_id:
                        continue

                    # Filtro de seguridad
                    validator = SecurityValidator(db)
                    check = validator.check_incoming_message(text)
                    if check.status == "block":
                        await validator.log_event(
                            severity="critical", event_type="injection_attempt",
                            source="user_message", raw_content=text,
                            action_taken="blocked", pattern=check.pattern,
                        )
                        await send_security_alert(chat_id, "injection_attempt", "critical", text[:200])
                        await send_message(chat_id, "⚠️ Mensaje bloqueado por política de seguridad.")
                        continue

                    session = await _get_or_create_telegram_session(db, chat_id)
                    prior_messages = await _load_prior_messages(db, session.id)

                    runner = AgentRunner(db)
                    result = await runner.run_routed(
                        message=text,
                        session_id=session.id,
                        prior_messages=prior_messages,
                        channel="telegram",
                    )

                    if result.blocked:
                        await send_message(chat_id, f"⛔ {result.blocked_reason}")
                        continue

                    if result.pending_approval_id:
                        from app.telegram.client import send_with_approval
                        approval_result = await db.execute(
                            select(PendingApproval).where(PendingApproval.id == result.pending_approval_id)
                        )
                        approval = approval_result.scalar_one_or_none()
                        if approval:
                            if result.text:
                                await send_message(chat_id, result.text)
                            await send_with_approval(
                                chat_id=chat_id,
                                tool_name=approval.tool_name,
                                tool_input=approval.tool_input,
                                approval_id=approval.id,
                            )
                        continue

                    response_text = result.text or "(sin respuesta)"
                    for chunk in _split_message(response_text):
                        await send_message(chat_id, chunk, parse_mode="HTML")

            except Exception as exc:
                logger.exception("Error procesando update %s: %s", update.get("update_id"), exc)
