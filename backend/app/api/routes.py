from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import get_agent
from app.agents.runner import AgentRunner
from app.api.deps import get_session, require_auth
from app.api.schemas import (
    ApprovalAction, ApprovalOut, ChatRequest, ChatResponse,
    MemoryIn, MemoryOut, MessageOut, SecurityEventOut, SessionOut,
)
from app.db.models import (
    Message, Memory, PendingApproval, SecurityEvent, Session as DBSession,
)
from app.db.session import AsyncSessionLocal
from app.memory.service import MemoryService
from app.security.validator import SecurityValidator

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
