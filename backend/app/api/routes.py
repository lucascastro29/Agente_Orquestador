from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import get_agent
from app.agents.runner import AgentRunner
from app.api.deps import get_session, require_auth
from app.api.schemas import (
    AgentOut, ApprovalAction, ApprovalOut, ChatRequest, ChatResponse,
    MemoryIn, MemoryOut, MessageOut, ScheduleTaskOut, SecurityEventOut, SessionOut, WorkerOut,
)
from app.db.models import (
    Message, Memory, PendingApproval, SecurityEvent, Session as DBSession, Worker,
)
from app.db.session import AsyncSessionLocal
from app.memory.service import MemoryService
from app.security.validator import SecurityValidator
from app.workers.manager import WorkerManager

router = APIRouter(prefix="/api", tags=["api"])


# --- Chat ---

@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> ChatResponse:
    # Filtro de seguridad
    validator = SecurityValidator(db)
    check = validator.check_incoming_message(req.message)
    if check.status == "block":
        await validator.log_event(
            severity="critical",
            event_type="injection_attempt",
            source="user_message",
            raw_content=req.message,
            action_taken="blocked",
            pattern=check.pattern,
        )
        return ChatResponse(
            session_id=req.session_id or "",
            text="",
            blocked=True,
            blocked_reason="Mensaje bloqueado por política de seguridad.",
        )

    # Obtener o crear sesión (agent_id default = orchestrator)
    session = await _get_or_create_session(db, req.session_id, req.agent_id)

    # Historial
    prior_messages = await _load_prior_messages(db, session.id)

    runner = AgentRunner(db)
    result = await runner.run_routed(
        message=req.message,
        session_id=session.id,
        prior_messages=prior_messages,
        channel="web",
    )

    return ChatResponse(
        session_id=session.id,
        text=result.text,
        blocked=result.blocked,
        blocked_reason=result.blocked_reason,
        pending_approval_id=result.pending_approval_id,
        cost=result.cost_detail,
    )


# --- Chat streaming (SSE) ---

@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    validator = SecurityValidator(db)
    check = validator.check_incoming_message(req.message)
    if check.status == "block":
        await validator.log_event(
            severity="critical",
            event_type="injection_attempt",
            source="user_message",
            raw_content=req.message,
            action_taken="blocked",
            pattern=check.pattern,
        )
        import json as _json
        async def _blocked():
            yield f"data: {_json.dumps({'type':'security_alert','severity':'critical','fragment':req.message[:200]})}\n\n"
            yield f"data: {_json.dumps({'type':'done'})}\n\n"
        return StreamingResponse(_blocked(), media_type="text/event-stream")

    session = await _get_or_create_session(db, req.session_id, req.agent_id)
    prior_messages = await _load_prior_messages(db, session.id)
    runner = AgentRunner(db)

    async def _generate():
        # Emitir session_id primero para que el cliente lo persista
        import json as _json
        yield f"data: {_json.dumps({'type':'session_id','session_id':session.id})}\n\n"
        async for chunk in runner.stream_run_routed(
            message=req.message,
            session_id=session.id,
            prior_messages=prior_messages,
        ):
            yield chunk

    return StreamingResponse(_generate(), media_type="text/event-stream",
                              headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


# --- Sessions ---

@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[SessionOut]:
    result = await db.execute(select(DBSession).order_by(DBSession.created_at.desc()))
    return [_session_out(s) for s in result.scalars().all()]


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(
    session_id: str,
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[MessageOut]:
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.position.asc())
    )
    return [_message_out(m) for m in result.scalars().all()]


# --- Memory ---

@router.get("/memory", response_model=list[MemoryOut])
async def list_memory(
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[MemoryOut]:
    svc = MemoryService(db)
    entries = await svc.get_relevant(limit=100)
    return [_memory_out(e) for e in entries]


@router.post("/memory", response_model=MemoryOut)
async def create_memory(
    body: MemoryIn,
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> MemoryOut:
    svc = MemoryService(db)
    entry = await svc.upsert(key=body.key, value={"text": body.value}, category=body.category)
    return _memory_out(entry)


@router.delete("/memory/{memory_id}")
async def delete_memory(
    memory_id: str,
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> dict:
    svc = MemoryService(db)
    deleted = await svc.delete_by_id(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return {"ok": True}


# --- Approvals ---

@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[ApprovalOut]:
    result = await db.execute(
        select(PendingApproval)
        .where(PendingApproval.status == "pending")
        .order_by(PendingApproval.created_at.desc())
    )
    return [_approval_out(a) for a in result.scalars().all()]


@router.post("/approvals/{approval_id}", response_model=ApprovalOut)
async def resolve_approval(
    approval_id: str,
    body: ApprovalAction,
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> ApprovalOut:
    result = await db.execute(
        select(PendingApproval).where(PendingApproval.id == approval_id)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="Approval already resolved")

    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    approval.status = "approved" if body.action == "approve" else "rejected"
    approval.resolved_at = datetime.now(timezone.utc)
    if body.edited_input:
        approval.edited_input = body.edited_input
        approval.status = "edited"
    await db.commit()
    await db.refresh(approval)
    return _approval_out(approval)


# --- Security events ---

@router.get("/security/events", response_model=list[SecurityEventOut])
async def list_security_events(
    resolved: bool | None = None,
    severity: str | None = None,
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[SecurityEventOut]:
    q = select(SecurityEvent).order_by(SecurityEvent.created_at.desc())
    if resolved is not None:
        q = q.where(SecurityEvent.resolved == resolved)
    if severity:
        q = q.where(SecurityEvent.severity == severity)
    result = await db.execute(q)
    return [_security_event_out(e) for e in result.scalars().all()]


@router.post("/security/events/{event_id}/resolve")
async def resolve_security_event(
    event_id: str,
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> dict:
    result = await db.execute(select(SecurityEvent).where(SecurityEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.resolved = True
    await db.commit()
    return {"ok": True}


# --- Workers ---

@router.get("/workers", response_model=list[WorkerOut])
async def list_workers(
    active_only: bool = False,
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[WorkerOut]:
    mgr = WorkerManager(db)
    workers = await mgr.get_active() if active_only else await mgr.get_all()
    return [_worker_out(w) for w in workers]


@router.get("/workers/{worker_id}", response_model=WorkerOut)
async def get_worker(
    worker_id: str,
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> WorkerOut:
    mgr = WorkerManager(db)
    worker = await mgr.get_by_id(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    return _worker_out(worker)


@router.post("/workers/{worker_id}/cancel")
async def cancel_worker(
    worker_id: str,
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> dict:
    mgr = WorkerManager(db)
    cancelled = await mgr.cancel(worker_id)
    if not cancelled:
        raise HTTPException(status_code=409, detail="Worker cannot be cancelled")
    return {"ok": True}


@router.post("/workers/hook")
async def workers_hook(
    payload: dict,
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Recibe eventos de Claude Code (Stop, Notification) vía scripts/notify_stop.py."""
    event_type = payload.get("event_type", "")
    data = payload.get("payload", {})

    if event_type == "Stop":
        return await _handle_cc_stop(db, data)
    elif event_type == "Notification":
        await _handle_cc_notification(data)
        return {"ok": True}

    return {"ok": True, "event_type": event_type}


async def _handle_cc_stop(db: AsyncSession, data: dict) -> dict:
    """Stop event: crea Worker, resume con Haiku y notifica por Telegram."""
    from app.config import settings as app_settings
    import anthropic

    cwd = data.get("cwd", "")
    cc_session_id = data.get("session_id", "")
    transcript_excerpt = data.get("transcript_excerpt", "")

    # Crear sesión de DB para este evento externo
    db_session = DBSession(
        agent_id="external_cc",
        channel="hook",
        title=f"cc:{cc_session_id[:8] if cc_session_id else cwd.split('/')[-1]}",
    )
    db.add(db_session)
    await db.commit()
    await db.refresh(db_session)

    mgr = WorkerManager(db)
    worker = await mgr.create(
        agent_id="external_cc",
        session_id=db_session.id,
        type="claude_code",
        prompt=transcript_excerpt[:200] or f"Sesión CC en {cwd}",
        working_dir=cwd,
    )
    await mgr.update_status(worker.id, status="done",
                             output=transcript_excerpt,
                             result_summary=transcript_excerpt[:300])

    # Generar resumen con Haiku si hay transcript
    summary = ""
    if transcript_excerpt and app_settings.anthropic_api_key:
        try:
            client = anthropic.AsyncAnthropic(api_key=app_settings.anthropic_api_key)
            resp = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                system=(
                    "Resumí en 2-3 oraciones qué hizo Claude Code en esta sesión. "
                    "Formato: qué se hizo, estado final (terminó/quedó pendiente), "
                    "si hubo errores. Sé directo, sin intro."
                ),
                messages=[{"role": "user", "content": transcript_excerpt[:3000]}],
            )
            summary = resp.content[0].text.strip()
        except Exception:
            summary = transcript_excerpt[:400]

    # Notificar por Telegram
    if app_settings.telegram_allowed_chat_id:
        from app.telegram.client import send_message
        dir_name = cwd.split("/")[-1] if cwd else "?"
        msg = (
            f"🏁 <b>Claude Code terminó</b>\n"
            f"📁 {dir_name}\n"
            f"🔑 <code>{cc_session_id[:12] if cc_session_id else '?'}</code>\n"
        )
        if summary:
            msg += f"\n📋 <b>Resumen:</b>\n{summary}"
        else:
            msg += "\n<i>(sin transcript disponible)</i>"
        msg += f"\n\n🆔 Worker: <code>{worker.id[:8]}</code>"
        await send_message(app_settings.telegram_allowed_chat_id, msg)

    return {"ok": True, "worker_id": worker.id}


async def _handle_cc_notification(data: dict) -> None:
    """Notification event: reenvía el mensaje directo a Telegram."""
    from app.config import settings as app_settings

    if not app_settings.telegram_allowed_chat_id:
        return

    title = data.get("title", "Claude Code")
    message = data.get("message", "")
    if not message:
        return

    from app.telegram.client import send_message
    await send_message(
        app_settings.telegram_allowed_chat_id,
        f"🔔 <b>{title}</b>\n{message}",
    )


# --- Agents dashboard ---

@router.get("/agents", response_model=list[AgentOut])
async def list_agents(
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[AgentOut]:
    from sqlalchemy import func
    from app.agents.config import AGENTS
    from app.agents.subagent_registry import SUB_AGENTS
    from app.tools.registry import registry as tool_registry

    # Contar workers activos y sesiones por agent_id
    active_q = await db.execute(
        select(Worker.agent_id, func.count(Worker.id).label("cnt"))
        .where(Worker.status.in_(["pending", "running", "waiting_input"]))
        .group_by(Worker.agent_id)
    )
    active_by_agent: dict[str, int] = {r.agent_id: r.cnt for r in active_q}

    sessions_q = await db.execute(
        select(DBSession.agent_id, func.count(DBSession.id).label("cnt"))
        .group_by(DBSession.agent_id)
    )
    sessions_by_agent: dict[str, int] = {r.agent_id: r.cnt for r in sessions_q}

    result: list[AgentOut] = []

    # Orquestador
    for agent in AGENTS.values():
        tools = tool_registry.names() if agent.allowed_tools is None else agent.allowed_tools
        result.append(AgentOut(
            id=agent.id,
            type="orchestrator",
            model=agent.model,
            tools=tools,
            max_workers=None,
            approval_policy=agent.approval_policy,
            active_workers=active_by_agent.get(agent.id, 0),
            total_sessions=sessions_by_agent.get(agent.id, 0),
        ))

    # Sub-agentes
    for sub in SUB_AGENTS.values():
        result.append(AgentOut(
            id=sub.id,
            type="subagent",
            model=sub.model,
            tools=sub.allowed_tools,
            max_workers=sub.max_workers,
            approval_policy=sub.approval_policy,
            active_workers=active_by_agent.get(sub.id, 0),
            total_sessions=sessions_by_agent.get(sub.id, 0),
        ))

    return result


@router.get("/schedule", response_model=list[ScheduleTaskOut])
async def list_schedule(
    _: str = Depends(require_auth),
    db: AsyncSession = Depends(get_session),
) -> list[ScheduleTaskOut]:
    from app.config import settings as app_settings
    from app.db.models import WatcherState
    from sqlalchemy import select as sa_select

    # Leer últimos checkeos de los watchers
    states_q = await db.execute(sa_select(WatcherState))
    states: dict[str, WatcherState] = {s.watcher: s for s in states_q.scalars().all()}

    mail_state = states.get("mail")
    cal_state = states.get("calendar")

    return [
        ScheduleTaskOut(
            name="check_mail",
            label="Watcher Gmail",
            schedule="cada 15 min",
            enabled=app_settings.gmail_watcher_enabled,
            last_checked_at=mail_state.last_checked_at if mail_state else None,
        ),
        ScheduleTaskOut(
            name="check_calendar",
            label="Watcher Calendar",
            schedule="cada 30 min",
            enabled=app_settings.calendar_watcher_enabled,
            last_checked_at=cal_state.last_checked_at if cal_state else None,
        ),
    ]


# --- Helpers ---

async def _get_or_create_session(
    db: AsyncSession, session_id: str | None, agent_id: str
) -> DBSession:
    if session_id:
        result = await db.execute(select(DBSession).where(DBSession.id == session_id))
        session = result.scalar_one_or_none()
        if session:
            return session
    session = DBSession(agent_id=agent_id, channel="web")
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
    return [{"role": m.role, "content": m.content} for m in result.scalars().all()]


def _session_out(s: DBSession) -> SessionOut:
    return SessionOut(
        id=s.id, agent_id=s.agent_id, title=s.title, channel=s.channel,
        total_cost_usd=s.total_cost_usd, created_at=s.created_at, updated_at=s.updated_at,
    )


def _message_out(m: Message) -> MessageOut:
    return MessageOut(
        id=m.id, session_id=m.session_id, position=m.position, role=m.role,
        content=m.content, model=m.model, input_tokens=m.input_tokens,
        output_tokens=m.output_tokens, cost_usd=m.cost_usd, created_at=m.created_at,
    )


def _memory_out(e: Memory) -> MemoryOut:
    return MemoryOut(
        id=e.id, key=e.key, value=e.value, category=e.category,
        created_at=e.created_at, updated_at=e.updated_at,
    )


def _approval_out(a: PendingApproval) -> ApprovalOut:
    return ApprovalOut(
        id=a.id, session_id=a.session_id, tool_name=a.tool_name,
        tool_input=a.tool_input, status=a.status, created_at=a.created_at,
    )


def _security_event_out(e: SecurityEvent) -> SecurityEventOut:
    return SecurityEventOut(
        id=e.id, severity=e.severity, event_type=e.event_type, source=e.source,
        raw_content=e.raw_content, pattern=e.pattern, action_taken=e.action_taken,
        resolved=e.resolved, created_at=e.created_at,
    )


def _worker_out(w: Worker) -> WorkerOut:
    return WorkerOut(
        id=w.id, parent_id=w.parent_id, agent_id=w.agent_id, session_id=w.session_id,
        type=w.type, status=w.status, prompt=w.prompt, working_dir=w.working_dir,
        result_summary=w.result_summary, cost_usd=w.cost_usd,
        notion_task_id=w.notion_task_id, error=w.error, notified=w.notified,
        created_at=w.created_at, started_at=w.started_at, finished_at=w.finished_at,
    )
