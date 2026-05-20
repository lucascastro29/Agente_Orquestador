"""Polling mode — alternativa a webhook, no requiere URL pública."""
import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot"
_offset: int = 0


async def _transcribe_telegram_voice(voice: dict, chat_id: str) -> str:
    """Descarga el audio de Telegram y lo transcribe con Whisper. Devuelve '' si falla."""
    from app.transcription.whisper import transcribe
    from app.telegram.client import send_message

    file_id = voice.get("file_id", "")
    if not file_id:
        return ""

    try:
        # Obtener path del archivo
        async with httpx.AsyncClient(timeout=15) as client:
            info = await client.get(
                f"{_BASE}{settings.telegram_bot_token}/getFile",
                params={"file_id": file_id},
            )
            info.raise_for_status()
            file_path = info.json()["result"]["file_path"]

            # Descargar el audio
            audio_resp = await client.get(
                f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
            )
            audio_resp.raise_for_status()
            audio_bytes = audio_resp.content

        filename = file_path.split("/")[-1] or "voice.ogg"
        await send_message(chat_id, "🎙 Transcribiendo audio…")
        text = await transcribe(audio_bytes, filename=filename)
        if text:
            await send_message(chat_id, f"📝 <i>{text}</i>", parse_mode="HTML")
        return text

    except RuntimeError as exc:
        # Whisper no configurado
        await send_message(chat_id, f"⚠️ {exc}")
        return ""
    except Exception as exc:
        logger.error("Error transcribiendo audio de Telegram: %s", exc)
        await send_message(chat_id, "⚠️ No pude transcribir el audio.")
        return ""


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

                    if not chat_id:
                        continue

                    if settings.telegram_allowed_chat_id and chat_id != settings.telegram_allowed_chat_id:
                        continue

                    # Transcribir voz/audio antes de procesar
                    text = message.get("text", "").strip()
                    voice = message.get("voice") or message.get("audio")
                    if voice and not text:
                        text = await _transcribe_telegram_voice(voice, chat_id)
                        if not text:
                            continue

                    if not text:
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

                    # TTS: sintetizar respuesta y enviar como audio de voz
                    try:
                        from app.tts.service import tts_service
                        from app.telegram.client import send_voice
                        ogg = await tts_service.synthesize_ogg(result.text or "")
                        if ogg:
                            await send_voice(chat_id, ogg)
                    except Exception as _tts_exc:
                        logger.debug("TTS Telegram error (no crítico): %s", _tts_exc)

            except Exception as exc:
                logger.exception("Error procesando update %s: %s", update.get("update_id"), exc)
