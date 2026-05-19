import json
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runner import AgentRunner
from app.config import settings
from app.db.models import Message, PendingApproval, Session as DBSession
from app.db.session import AsyncSessionLocal
from app.security.validator import SecurityValidator
from app.telegram.client import send_message, send_with_approval, send_security_alert

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
) -> dict:
    # Validar secret
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid secret")

    body = await request.json()

    async with AsyncSessionLocal() as db:
        # Callback query (botón inline presionado)
        if "callback_query" in body:
            await _handle_callback(body["callback_query"], db)
            return {"ok": True}

        # Mensaje de texto
        message = body.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()

        if not chat_id or not text:
            return {"ok": True}

        # Validar chat permitido
        if settings.telegram_allowed_chat_id and chat_id != settings.telegram_allowed_chat_id:
            return {"ok": True}

        # Filtro de seguridad sobre el mensaje entrante
        validator = SecurityValidator(db)
        check = validator.check_incoming_message(text)

        if check.status == "block":
            await validator.log_event(
                severity="critical",
                event_type="injection_attempt",
                source="user_message",
                raw_content=text,
                action_taken="blocked",
                pattern=check.pattern,
            )
            await send_security_alert(chat_id, "injection_attempt", "critical", text[:200])
            await send_message(chat_id, "⚠️ Mensaje bloqueado por política de seguridad.")
            return {"ok": True}

        # Obtener o crear sesión Telegram
        session = await _get_or_create_telegram_session(db, chat_id)

        # Cargar historial de mensajes de la sesión
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
            return {"ok": True}

        if result.pending_approval_id:
            # Recuperar datos de la aprobación para mostrar el botón
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
            return {"ok": True}

        # Enviar respuesta (Telegram tiene límite de 4096 chars por mensaje)
        response_text = result.text or "(sin respuesta)"
        for chunk in _split_message(response_text):
            await send_message(chat_id, chunk)

    return {"ok": True}


async def _handle_callback(callback: dict, db: AsyncSession) -> None:
    chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
    data = callback.get("data", "")

    if ":" not in data:
        return

    action, approval_id = data.split(":", 1)

    result = await db.execute(
        select(PendingApproval).where(PendingApproval.id == approval_id)
    )
    approval = result.scalar_one_or_none()
    if not approval or approval.status != "pending":
        await send_message(chat_id, "Esta acción ya fue procesada.")
        return

    if action == "approve":
        approval.status = "approved"
        approval.resolved_at = datetime.now(timezone.utc)
        await db.commit()

        # Reanudar el runner con la tool aprobada — la tool se ejecuta ahora
        # como si requires_confirmation fuera False
        tool_from_registry = __import__("app.tools.registry", fromlist=["registry"]).registry.get(
            approval.tool_name
        )
        if tool_from_registry:
            memory_svc = __import__("app.memory.service", fromlist=["MemoryService"]).MemoryService(db)
            try:
                if approval.tool_name in ("get_memoria", "update_memoria", "delete_memoria", "search_memoria"):
                    output = await tool_from_registry.handler(memory_svc, **approval.tool_input)
                else:
                    output = await tool_from_registry.handler(**approval.tool_input)
                await send_message(chat_id, f"✅ Ejecutado.\n<pre>{str(output)[:500]}</pre>")
            except Exception as exc:
                await send_message(chat_id, f"❌ Error al ejecutar: {exc}")
        else:
            await send_message(chat_id, "✅ Acción aprobada (tool no disponible localmente).")

    elif action == "reject":
        approval.status = "rejected"
        approval.resolved_at = datetime.now(timezone.utc)
        await db.commit()
        await send_message(chat_id, "✗ Acción cancelada.")


async def _get_or_create_telegram_session(db: AsyncSession, chat_id: str) -> DBSession:
    result = await db.execute(
        select(DBSession).where(
            DBSession.external_chat_id == chat_id,
            DBSession.channel == "telegram",
        ).order_by(DBSession.created_at.desc()).limit(1)
    )
    session = result.scalar_one_or_none()
    if not session:
        session = DBSession(
            agent_id="orchestrator",
            channel="telegram",
            external_chat_id=chat_id,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return session


async def _load_prior_messages(db: AsyncSession, session_id: str) -> list[dict]:
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.position.asc())
    )
    messages = result.scalars().all()
    return [{"role": m.role, "content": m.content} for m in messages]


def _split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        chunks.append(text[:limit])
        text = text[limit:]
    return chunks
