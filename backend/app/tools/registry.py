from dataclasses import dataclass, field
from collections.abc import Callable, Awaitable
from typing import Any


@dataclass
class LocalTool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[..., Awaitable[Any]]
    requires_confirmation: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, LocalTool] = {}

    def register(self, tool: LocalTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> LocalTool | None:
        return self._tools.get(name)

    def all(self) -> list[LocalTool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def to_anthropic_tools(self, names: list[str] | None = None) -> list[dict]:
        tools = self.all() if names is None else [t for t in self.all() if t.name in names]
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]


# --- Instancia global ---
registry = ToolRegistry()


# --- Handlers de memoria (se registran al importar este módulo) ---

_MEMORY_CATEGORIES = [
    "objetivo_actual", "proyecto", "preferencia", "persona",
    "recordatorio", "nota_libre", "sesion_pasada",
]


async def _handle_get_memoria(memory_service: Any, categories: list[str] | None = None, limit: int = 20) -> dict:
    entries = await memory_service.get_relevant(limit=limit, categories=categories)
    return {"memoria": memory_service.format_for_prompt(entries)}


async def _handle_update_memoria(memory_service: Any, key: str, value: str, category: str) -> dict:
    entry = await memory_service.upsert(key=key, value={"text": value}, category=category)
    return {"ok": True, "id": entry.id, "key": key, "category": category}


async def _handle_delete_memoria(memory_service: Any, key: str, category: str) -> dict:
    deleted = await memory_service.delete(key=key, category=category)
    return {"ok": deleted}


async def _handle_search_memoria(memory_service: Any, query: str, limit: int = 10) -> dict:
    entries = await memory_service.search(query=query, limit=limit)
    return {"results": [{"key": e.key, "category": e.category, "value": e.value} for e in entries]}


registry.register(LocalTool(
    name="get_memoria",
    description="Recupera entradas de la memoria del orquestador. Filtrá por categorías para obtener contexto relevante.",
    input_schema={
        "type": "object",
        "properties": {
            "categories": {
                "type": "array",
                "items": {"type": "string", "enum": _MEMORY_CATEGORIES},
                "description": "Categorías a consultar. Si se omite, devuelve las 20 entradas más recientes.",
            },
            "limit": {"type": "integer", "default": 20},
        },
    },
    handler=_handle_get_memoria,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="update_memoria",
    description="Guarda o actualiza una entrada en la memoria del orquestador.",
    input_schema={
        "type": "object",
        "properties": {
            "key":      {"type": "string", "description": "Identificador único de la entrada."},
            "value":    {"type": "string", "description": "Contenido a guardar."},
            "category": {"type": "string", "enum": _MEMORY_CATEGORIES},
        },
        "required": ["key", "value", "category"],
    },
    handler=_handle_update_memoria,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="delete_memoria",
    description="Elimina una entrada de la memoria por key y categoría.",
    input_schema={
        "type": "object",
        "properties": {
            "key":      {"type": "string"},
            "category": {"type": "string", "enum": _MEMORY_CATEGORIES},
        },
        "required": ["key", "category"],
    },
    handler=_handle_delete_memoria,
    requires_confirmation=True,
))

registry.register(LocalTool(
    name="search_memoria",
    description="Busca entradas en la memoria por texto.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
    handler=_handle_search_memoria,
    requires_confirmation=False,
))


# --- Tools de workers y Notion (Fase 4) ---

async def _handle_run_claude_code(
    worker_manager: Any,
    session_id: str,
    prompt: str,
    working_dir: str,
    mode: str = "background",
    notify_on_done: bool = True,
    notion_task_id: str | None = None,
) -> dict:
    from app.config import settings
    if settings.allowed_working_dirs and not any(
        working_dir.startswith(d) for d in settings.allowed_working_dirs
    ):
        return {
            "error": (
                f"working_dir '{working_dir}' no está permitido. "
                f"Directorios permitidos: {settings.allowed_working_dirs}"
            )
        }
    worker = await worker_manager.create(
        agent_id="orchestrator",
        session_id=session_id,
        type="claude_code",
        prompt=prompt,
        working_dir=working_dir,
        notion_task_id=notion_task_id,
    )
    # Despachar tarea Celery
    from app.workers.tasks import execute_claude_code
    execute_claude_code.delay(worker.id, prompt, working_dir)
    return {"worker_id": worker.id, "status": "pending", "mode": mode}


async def _handle_get_workers_status(worker_manager: Any) -> dict:
    workers = await worker_manager.get_active()
    return {
        "active_workers": [
            {
                "id": w.id,
                "status": w.status,
                "type": w.type,
                "prompt": w.prompt[:80],
                "working_dir": w.working_dir,
                "started_at": w.started_at.isoformat() if w.started_at else None,
            }
            for w in workers
        ]
    }


async def _handle_cancel_worker(worker_manager: Any, worker_id: str) -> dict:
    cancelled = await worker_manager.cancel(worker_id)
    return {"ok": cancelled, "worker_id": worker_id}


async def _handle_get_notion_tasks(board: str, label: str = "CLAUDE CODE") -> dict:
    from app.notion.task_sync import NotionTaskSync
    sync = NotionTaskSync()
    tasks = await sync.get_tasks_by_label(board, label)
    return {
        "tasks": [
            {"id": t.id, "title": t.title, "status": t.status, "url": t.url}
            for t in tasks
        ]
    }


async def _handle_notion_search(query: str = "", page_size: int = 20) -> dict:
    from app.notion.task_sync import NotionTaskSync
    sync = NotionTaskSync()
    items = await sync.search_pages(query=query, page_size=page_size)
    return {"results": items, "count": len(items)}


async def _handle_notion_list_database(board: str, page_size: int = 50) -> dict:
    from app.notion.task_sync import NotionTaskSync
    sync = NotionTaskSync()
    items = await sync.list_database_items(board=board, page_size=page_size)
    return {"items": items, "count": len(items)}


async def _handle_notion_get_page(page_id: str) -> dict:
    from app.notion.task_sync import NotionTaskSync
    sync = NotionTaskSync()
    return await sync.get_page_content(page_id=page_id)


async def _handle_notion_create_task(
    board: str,
    title: str,
    status: str | None = None,
    description: str | None = None,
) -> dict:
    from app.notion.task_sync import NotionTaskSync
    sync = NotionTaskSync()
    return await sync.create_task(board=board, title=title, status=status, description=description)


registry.register(LocalTool(
    name="run_claude_code",
    description=(
        "Lanza una Claude Code session en background para ejecutar una tarea técnica. "
        "Siempre requiere working_dir dentro de ALLOWED_WORKING_DIRS."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "prompt":         {"type": "string", "description": "Instrucción completa para Claude Code."},
            "working_dir":    {"type": "string", "description": "Directorio de trabajo absoluto."},
            "mode":           {"type": "string", "enum": ["background", "sync"], "default": "background"},
            "notify_on_done": {"type": "boolean", "default": True},
            "notion_task_id": {"type": "string"},
        },
        "required": ["prompt", "working_dir"],
    },
    handler=_handle_run_claude_code,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="get_workers_status",
    description="Devuelve el estado de todos los workers activos (pending, running, waiting_input).",
    input_schema={"type": "object", "properties": {}},
    handler=_handle_get_workers_status,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="cancel_worker",
    description="Cancela un worker en curso.",
    input_schema={
        "type": "object",
        "properties": {"worker_id": {"type": "string"}},
        "required": ["worker_id"],
    },
    handler=_handle_cancel_worker,
    requires_confirmation=True,
))

registry.register(LocalTool(
    name="notion_get_tasks",
    description="Lee tareas de un tablero de Notion filtradas por etiqueta.",
    input_schema={
        "type": "object",
        "properties": {
            "board": {"type": "string", "description": "Nombre exacto del tablero en NOTION_WATCHED_BOARDS."},
            "label": {"type": "string", "default": "CLAUDE CODE", "description": "Etiqueta a filtrar."},
        },
        "required": ["board"],
    },
    handler=_handle_get_notion_tasks,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="notion_search",
    description=(
        "Busca páginas y bases de datos en el workspace de Notion por texto libre. "
        "Usá query vacío ('') para listar todo lo accesible."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query":     {"type": "string", "description": "Texto a buscar. Vacío lista todo.", "default": ""},
            "page_size": {"type": "integer", "default": 20},
        },
    },
    handler=_handle_notion_search,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="notion_list_database",
    description="Lista todos los items de un tablero/base de datos de Notion sin filtro de etiqueta.",
    input_schema={
        "type": "object",
        "properties": {
            "board":     {"type": "string", "description": "Nombre exacto del tablero (debe estar en NOTION_WATCHED_BOARDS)."},
            "page_size": {"type": "integer", "default": 50},
        },
        "required": ["board"],
    },
    handler=_handle_notion_list_database,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="notion_get_page",
    description="Lee el contenido completo de una página de Notion dado su ID.",
    input_schema={
        "type": "object",
        "properties": {
            "page_id": {"type": "string", "description": "ID de la página (UUID sin guiones o con guiones)."},
        },
        "required": ["page_id"],
    },
    handler=_handle_notion_get_page,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="notion_create_task",
    description=(
        "Crea una nueva tarea/página en un tablero de Notion. "
        "Usá notion_search o notion_list_database primero si no sabés el nombre exacto del tablero."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "board":       {"type": "string", "description": "Nombre exacto del tablero (debe estar en NOTION_WATCHED_BOARDS)."},
            "title":       {"type": "string", "description": "Título de la tarea."},
            "status":      {"type": "string", "description": "Estado inicial (ej: 'Por hacer', 'En progreso'). Opcional."},
            "description": {"type": "string", "description": "Descripción o detalle de la tarea. Opcional."},
        },
        "required": ["board", "title"],
    },
    handler=_handle_notion_create_task,
    requires_confirmation=True,
))


# --- Tools de sub-agentes (Fase 5) ---

async def _handle_create_subagent(
    worker_manager: Any,
    session_id: str,
    type: str,
    name: str,
    objective: str,
    working_dir: str | None = None,
    notion_task_id: str | None = None,
    notify_on_done: bool = True,  # noqa: ARG001 — reservado para uso futuro
) -> dict:
    from app.agents.subagent_registry import get_subagent, SUB_AGENTS

    # Validar type explícitamente antes de hacer nada
    if type not in SUB_AGENTS:
        return {
            "error": (
                f"Tipo de sub-agente inválido: '{type}'. "
                f"Tipos válidos: {list(SUB_AGENTS.keys())}. "
                "Usá el parámetro 'type' con uno de esos valores exactos."
            )
        }

    sub_cfg = get_subagent(type)

    worker = await worker_manager.create(
        agent_id=sub_cfg.id,
        session_id=session_id,
        type="subagent",
        prompt=f"[{name}] {objective}",
        working_dir=working_dir,
        notion_task_id=notion_task_id,
    )

    # Chequeo obligatorio: verificar que el worker quedó guardado en DB antes de reportar éxito
    import asyncio as _asyncio
    await _asyncio.sleep(0.1)  # flush del commit
    worker_check = await worker_manager.get_by_id(worker.id)
    if worker_check is None:
        return {
            "error": (
                f"El worker del sub-agente '{name}' no se pudo persistir en DB. "
                "El sub-agente NO fue lanzado. Intentá de nuevo."
            )
        }

    from app.workers.tasks import execute_subagent
    execute_subagent.delay(worker.id, type, objective, working_dir, session_id)

    # Verificar que Celery aceptó la tarea (comprobación de conexión a Redis)
    try:
        from app.worker import celery_app
        celery_app.control.ping(timeout=1)
        celery_ok = True
    except Exception:
        celery_ok = False

    return {
        "ok": True,
        "worker_id": worker.id,
        "worker_status": worker_check.status,
        "subagent_type": type,
        "name": name,
        "objective_preview": objective[:120],
        "working_dir": working_dir,
        "celery_broker_ok": celery_ok,
        "message": (
            f"Sub-agente '{name}' (type={type}) lanzado correctamente. "
            f"Worker ID: {worker.id}. "
            f"Podés monitorear con get_workers_status()."
        ),
    }


# --- Tool: remember_session (Fase 9) ---

async def _handle_remember_session(db: Any, session_id: str, label: str | None = None) -> dict:
    """Carga mensajes de la sesión actual, los resume con Haiku y guarda en memoria."""
    from app.db.models import Message
    from sqlalchemy import select
    import anthropic as _anthropic
    from app.config import settings
    from app.memory.service import MemoryService

    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.position.asc())
    )
    messages = result.scalars().all()
    if not messages:
        return {"error": "No hay mensajes en esta sesión."}

    conv_lines = []
    for m in messages:
        role = "Usuario" if m.role == "user" else "Orquestador"
        text = ""
        if isinstance(m.content, list):
            for block in m.content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += block.get("text", "")
        elif isinstance(m.content, str):
            text = m.content
        if text.strip():
            conv_lines.append(f"{role}: {text[:300]}")

    conv_text = "\n".join(conv_lines[:40])

    client = _anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system="Resumí esta conversación en 3-5 puntos clave. Solo lo más importante. Bullet points en español.",
            messages=[{"role": "user", "content": conv_text}],
        )
        summary = resp.content[0].text.strip()
    except Exception as exc:
        summary = f"Sesión con {len(messages)} mensajes. (Error al resumir: {exc})"

    svc = MemoryService(db)
    key = label or f"sesion_{session_id[:8]}"
    await svc.upsert(key=key, value={"text": summary, "session_id": session_id}, category="sesion_pasada")
    return {"ok": True, "key": key, "summary": summary[:300]}


registry.register(LocalTool(
    name="remember_session",
    description=(
        "Guarda un resumen de la sesión actual en la memoria persistente con categoría 'sesion_pasada'. "
        "Usalo cuando el usuario pida explícitamente recordar esta conversación o sesión."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Nombre descriptivo para identificar esta sesión. Ej: 'sesion_planning_mayo'. Opcional."},
        },
    },
    handler=_handle_remember_session,
    requires_confirmation=False,
))


# --- Tools: Gmail + Calendar activos (Fase 9) ---

import time as _time
_google_token_cache: dict = {"token": "", "expires_at": 0.0}


async def _get_google_access_token() -> str:
    """Devuelve un access token válido. Usa refresh token si está configurado,
    cae a gmail_oauth_token legacy si no."""
    from app.config import settings
    import httpx

    # Preferir refresh token (no vence)
    if settings.google_client_id and settings.google_client_secret and settings.google_refresh_token:
        now = _time.time()
        if _google_token_cache["token"] and now < _google_token_cache["expires_at"] - 60:
            return _google_token_cache["token"]
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "refresh_token": settings.google_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            r.raise_for_status()
            data = r.json()
            _google_token_cache["token"] = data["access_token"]
            _google_token_cache["expires_at"] = now + data.get("expires_in", 3600)
            return _google_token_cache["token"]

    # Fallback: access token legacy (puede estar vencido)
    return settings.gmail_oauth_token or settings.calendar_oauth_token


async def _handle_read_gmail_inbox(max_results: int = 10, only_unread: bool = True) -> dict:
    from app.config import settings
    if not settings.gmail_oauth_token and not settings.google_refresh_token:
        return {"error": "Gmail no configurado — agregá GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET y GOOGLE_REFRESH_TOKEN en .env"}
    import httpx
    token = await _get_google_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    q = "is:unread" if only_unread else ""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers,
            params={"maxResults": max_results, "q": q},
        )
        if r.status_code != 200:
            return {"error": f"Gmail API {r.status_code}: {r.text[:200]}"}
        msg_ids = [m["id"] for m in r.json().get("messages", [])]

        emails = []
        for mid in msg_ids:
            mr = await client.get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}",
                headers=headers,
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            )
            if mr.status_code == 200:
                data = mr.json()
                hdrs = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
                emails.append({
                    "id": mid,
                    "from": hdrs.get("From", ""),
                    "subject": hdrs.get("Subject", ""),
                    "date": hdrs.get("Date", ""),
                    "snippet": data.get("snippet", ""),
                })
    return {"emails": emails, "count": len(emails)}


registry.register(LocalTool(
    name="read_gmail_inbox",
    description="Lee los emails recientes del inbox de Gmail. Requiere GMAIL_OAUTH_TOKEN configurado.",
    input_schema={
        "type": "object",
        "properties": {
            "max_results": {"type": "integer", "default": 10, "description": "Máximo de emails a retornar."},
            "only_unread": {"type": "boolean", "default": True, "description": "Solo no leídos."},
        },
    },
    handler=_handle_read_gmail_inbox,
    requires_confirmation=False,
))


async def _handle_read_calendar_events(max_results: int = 10, days_ahead: int = 7) -> dict:
    from app.config import settings
    if not settings.calendar_oauth_token and not settings.google_refresh_token:
        return {"error": "Calendar no configurado — agregá GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET y GOOGLE_REFRESH_TOKEN en .env"}
    import httpx
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    time_max = now + timedelta(days=days_ahead)
    token = await _get_google_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "timeMin": now.isoformat(),
        "timeMax": time_max.isoformat(),
        "maxResults": max_results,
        "singleEvents": "true",
        "orderBy": "startTime",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers=headers,
            params=params,
        )
        if r.status_code != 200:
            return {"error": f"Calendar API {r.status_code}: {r.text[:200]}"}
        events = []
        for ev in r.json().get("items", []):
            start = ev.get("start", {})
            events.append({
                "id": ev.get("id"),
                "title": ev.get("summary", "Sin título"),
                "start": start.get("dateTime") or start.get("date", ""),
                "location": ev.get("location", ""),
                "attendees": [a.get("email") for a in ev.get("attendees", [])],
                "description": (ev.get("description") or "")[:200],
            })
    return {"events": events, "count": len(events)}


registry.register(LocalTool(
    name="read_calendar_events",
    description="Lee eventos próximos del Google Calendar. Requiere CALENDAR_OAUTH_TOKEN configurado.",
    input_schema={
        "type": "object",
        "properties": {
            "max_results": {"type": "integer", "default": 10},
            "days_ahead":  {"type": "integer", "default": 7, "description": "Días hacia adelante a consultar."},
        },
    },
    handler=_handle_read_calendar_events,
    requires_confirmation=False,
))


# --- Tool: notion_update_task ---

async def _handle_notion_update_task(
    task_id: str,
    status: str | None = None,
    description: str | None = None,
) -> dict:
    from app.notion.task_sync import NotionTaskSync
    sync = NotionTaskSync()
    return await sync.update_task(task_id=task_id, status=status, description=description)


registry.register(LocalTool(
    name="notion_update_task",
    description="Actualiza el estado y/o descripción de una tarea existente en Notion dado su ID.",
    input_schema={
        "type": "object",
        "properties": {
            "task_id":     {"type": "string", "description": "ID de la página Notion (UUID)."},
            "status":      {"type": "string", "description": "Nuevo estado. Ej: 'En progreso', 'Completado'."},
            "description": {"type": "string", "description": "Nuevo contenido de descripción."},
        },
        "required": ["task_id"],
    },
    handler=_handle_notion_update_task,
    requires_confirmation=True,
))


# --- Tools: Tareas Programadas (Fase 9) ---

async def _handle_schedule_task(
    db: Any,
    name: str,
    cron_expr: str,
    action_type: str,
    action_config: dict,
    description: str | None = None,
) -> dict:
    from croniter import croniter, CroniterBadCronError
    from datetime import datetime, timezone
    from app.db.models import ScheduledTask

    now = datetime.now(timezone.utc)
    try:
        itr = croniter(cron_expr, now)
        next_run = itr.get_next(datetime)
    except (CroniterBadCronError, Exception) as exc:
        return {"error": f"Expresión cron inválida '{cron_expr}': {exc}"}

    valid_types = ("message", "run_claude_code", "create_subagent")
    if action_type not in valid_types:
        return {"error": f"action_type debe ser uno de: {valid_types}"}

    task = ScheduledTask(
        name=name,
        description=description,
        cron_expr=cron_expr,
        action_type=action_type,
        action_config=action_config,
        next_run_at=next_run,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return {
        "id": task.id,
        "name": task.name,
        "cron_expr": cron_expr,
        "next_run_at": next_run.isoformat(),
        "action_type": action_type,
    }


async def _handle_list_scheduled_tasks(db: Any) -> dict:
    from app.db.models import ScheduledTask
    from sqlalchemy import select
    result = await db.execute(select(ScheduledTask).order_by(ScheduledTask.created_at.desc()))
    tasks = result.scalars().all()
    return {
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "cron_expr": t.cron_expr,
                "enabled": t.enabled,
                "action_type": t.action_type,
                "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
                "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
                "run_count": t.run_count,
                "last_error": t.last_error,
            }
            for t in tasks
        ]
    }


async def _handle_delete_scheduled_task(db: Any, task_id: str) -> dict:
    from app.db.models import ScheduledTask
    from sqlalchemy import select, delete as sa_delete
    result = await db.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return {"error": f"Tarea '{task_id}' no encontrada"}
    await db.execute(sa_delete(ScheduledTask).where(ScheduledTask.id == task_id))
    await db.commit()
    return {"ok": True, "deleted": task.name}


async def _handle_toggle_scheduled_task(db: Any, task_id: str, enabled: bool) -> dict:
    from app.db.models import ScheduledTask
    from sqlalchemy import select
    result = await db.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return {"error": f"Tarea '{task_id}' no encontrada"}
    task.enabled = enabled
    await db.commit()
    return {"ok": True, "name": task.name, "enabled": enabled}


registry.register(LocalTool(
    name="schedule_task",
    description=(
        "Crea una tarea programada con expresión cron. "
        "action_type='message': envía un mensaje al orquestador (action_config: {message: str}). "
        "action_type='run_claude_code': lanza Claude Code (action_config: {prompt, working_dir}). "
        "action_type='create_subagent': instancia sub-agente (action_config: {type, name, objective, working_dir?}). "
        "Cron examples: '0 9 * * 1-5' = lunes-viernes 9am | '0 8 * * *' = todos los días 8am."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name":         {"type": "string", "description": "Nombre descriptivo de la tarea."},
            "description":  {"type": "string", "description": "Para qué sirve esta tarea programada."},
            "cron_expr":    {"type": "string", "description": "Expresión cron estándar (5 campos)."},
            "action_type":  {"type": "string", "enum": ["message", "run_claude_code", "create_subagent"]},
            "action_config": {"type": "object", "description": "Config según action_type."},
        },
        "required": ["name", "cron_expr", "action_type", "action_config"],
    },
    handler=_handle_schedule_task,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="list_scheduled_tasks",
    description="Lista todas las tareas programadas con su próxima ejecución y estado.",
    input_schema={"type": "object", "properties": {}},
    handler=_handle_list_scheduled_tasks,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="delete_scheduled_task",
    description="Elimina una tarea programada por su ID.",
    input_schema={
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"],
    },
    handler=_handle_delete_scheduled_task,
    requires_confirmation=True,
))

registry.register(LocalTool(
    name="toggle_scheduled_task",
    description="Activa o desactiva una tarea programada sin eliminarla.",
    input_schema={
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "enabled": {"type": "boolean"},
        },
        "required": ["task_id", "enabled"],
    },
    handler=_handle_toggle_scheduled_task,
    requires_confirmation=False,
))


# --- Sub-agentes (ya registrado abajo, no duplicar) ---

registry.register(LocalTool(
    name="create_subagent",
    description=(
        "Instancia un sub-agente especializado. "
        "PARÁMETROS OBLIGATORIOS: 'type' (elige el agente) + 'name' (etiqueta descriptiva) + 'objective' (qué hacer). "
        "NO existen parámetros como max_workers, duration_minutes, policy ni model — no los inventes. "
        "TIPOS DISPONIBLES:\n"
        "  • type='sub_webdev': Frontend Engineer Next.js+Tailwind+animaciones Apple-style. "
        "Usalo para páginas web, landing pages, scroll effects, video scroll-driven. "
        "Siempre incluir en objective: ruta del repo en /workspace + estética buscada + feature a implementar.\n"
        "  • type='sub_dev': Dev backend/fullstack general. Para código de servidor, APIs, scripts, migraciones.\n"
        "  • type='sub_analista': Analista datos/investigación. Para reportes, análisis, síntesis de información.\n"
        "EJEMPLO CORRECTO: create_subagent(type='sub_webdev', name='landing-portfolioNext', "
        "objective='Implementá hero section con scroll animation en /workspace/portfolioNext. Estética Linear.', "
        "working_dir='/workspace/portfolioNext')"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["sub_webdev", "sub_dev", "sub_analista"],
                "description": "REQUERIDO. Tipo de sub-agente. 'sub_webdev' para web/frontend, 'sub_dev' para backend/general, 'sub_analista' para análisis.",
            },
            "name": {
                "type": "string",
                "description": "REQUERIDO. Etiqueta descriptiva para identificar esta instancia. Ej: 'landing-portfolioNext', 'analisis-inbox-mayo'.",
            },
            "objective": {
                "type": "string",
                "description": "REQUERIDO. Objetivo completo y detallado que debe lograr el sub-agente. Incluir todo el contexto necesario.",
            },
            "working_dir": {
                "type": "string",
                "description": "Directorio de trabajo dentro de ALLOWED_WORKING_DIRS. Para sub_webdev: ruta al repo. Ej: '/workspace/portfolioNext'.",
            },
            "notion_task_id": {
                "type": "string",
                "description": "ID de página Notion para actualizar al completar (opcional).",
            },
            "notify_on_done": {"type": "boolean", "default": True},
        },
        "required": ["type", "name", "objective"],
    },
    handler=_handle_create_subagent,
    requires_confirmation=False,
))


# --- Playbooks (Fase 10) ---

async def _handle_save_playbook(
    db: Any,
    name: str,
    steps: list,
    description: str | None = None,
    tags: list | None = None,
) -> dict:
    from app.db.models import Playbook
    p = Playbook(name=name, description=description, steps=steps, tags=tags or [])
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"ok": True, "playbook_id": p.id, "name": p.name, "steps_count": len(steps)}


async def _handle_list_playbooks(db: Any) -> dict:
    from app.db.models import Playbook
    from sqlalchemy import select
    result = await db.execute(select(Playbook).order_by(Playbook.created_at.desc()))
    playbooks = result.scalars().all()
    return {
        "playbooks": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "steps_count": len(p.steps or []),
                "tags": p.tags or [],
                "run_count": p.run_count,
                "last_run_at": p.last_run_at.isoformat() if p.last_run_at else None,
            }
            for p in playbooks
        ]
    }


async def _handle_get_playbook(db: Any, playbook_id: str) -> dict:
    from app.db.models import Playbook
    from sqlalchemy import select
    result = await db.execute(select(Playbook).where(Playbook.id == playbook_id))
    p = result.scalar_one_or_none()
    if not p:
        return {"error": f"Playbook '{playbook_id}' no encontrado"}
    return {"id": p.id, "name": p.name, "description": p.description, "steps": p.steps, "tags": p.tags}


async def _handle_run_playbook(db: Any, playbook_id: str) -> dict:
    """Devuelve los pasos al orquestador para que los ejecute en orden."""
    from app.db.models import Playbook
    from sqlalchemy import select
    from datetime import datetime, timezone
    result = await db.execute(select(Playbook).where(Playbook.id == playbook_id))
    p = result.scalar_one_or_none()
    if not p:
        return {"error": f"Playbook '{playbook_id}' no encontrado"}
    p.run_count = (p.run_count or 0) + 1
    p.last_run_at = datetime.now(timezone.utc)
    await db.commit()
    steps_text = "\n".join(
        f"{i+1}. [{s.get('label', s.get('tool', ''))}] "
        f"Llamá tool='{s['tool']}' con params={s.get('params', {})}"
        for i, s in enumerate(p.steps or [])
    )
    return {
        "playbook": p.name,
        "description": p.description,
        "steps_to_execute": p.steps,
        "instructions": (
            f"Ejecutá los siguientes pasos EN ORDEN usando tus tools. "
            f"Reportá el resultado de cada uno antes de pasar al siguiente.\n\n{steps_text}"
        ),
    }


async def _handle_update_playbook(
    db: Any,
    playbook_id: str,
    name: str | None = None,
    description: str | None = None,
    steps: list | None = None,
    tags: list | None = None,
) -> dict:
    from app.db.models import Playbook
    from sqlalchemy import select
    result = await db.execute(select(Playbook).where(Playbook.id == playbook_id))
    p = result.scalar_one_or_none()
    if not p:
        return {"error": f"Playbook '{playbook_id}' no encontrado"}
    if name is not None:
        p.name = name
    if description is not None:
        p.description = description
    if steps is not None:
        p.steps = steps
    if tags is not None:
        p.tags = tags
    await db.commit()
    return {"ok": True, "playbook_id": p.id, "name": p.name}


async def _handle_delete_playbook(db: Any, playbook_id: str) -> dict:
    from app.db.models import Playbook
    from sqlalchemy import select, delete as sa_delete
    result = await db.execute(select(Playbook).where(Playbook.id == playbook_id))
    p = result.scalar_one_or_none()
    if not p:
        return {"error": f"Playbook '{playbook_id}' no encontrado"}
    await db.execute(sa_delete(Playbook).where(Playbook.id == playbook_id))
    await db.commit()
    return {"ok": True, "deleted": p.name}


async def _handle_github_create_pr(
    repo: str,
    title: str,
    head: str,
    base: str = "main",
    body: str = "",
) -> dict:
    """Abre un Pull Request en GitHub via API. Requiere GITHUB_TOKEN en .env."""
    from app.config import settings
    if not settings.github_token:
        return {"error": "GITHUB_TOKEN no configurado en .env — agregalo para habilitar GitHub integration."}
    if "/" not in repo:
        if not settings.github_username:
            return {"error": "GITHUB_USERNAME no configurado en .env — necesario cuando repo no incluye owner (ej: 'mi-repo')."}
        owner, repo_name = settings.github_username, repo
    else:
        owner, repo_name = repo.split("/", 1)
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.github.com/repos/{owner}/{repo_name}/pulls",
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"title": title, "head": head, "base": base, "body": body},
            timeout=30.0,
        )
    if r.status_code in (200, 201):
        data = r.json()
        return {
            "ok": True,
            "pr_url": data["html_url"],
            "pr_number": data["number"],
            "title": data["title"],
            "state": data["state"],
        }
    return {"error": f"GitHub API {r.status_code}: {r.text[:400]}"}


registry.register(LocalTool(
    name="github_create_pr",
    description=(
        "Abre un Pull Request en GitHub. Usá después de que el sub-agente pusheó una rama. "
        "Si repo no incluye owner (ej: 'mi-repo'), usa GITHUB_USERNAME del .env. "
        "Formato repo: 'mi-repo' o 'owner/mi-repo'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "repo":  {"type": "string", "description": "Nombre del repo ('mi-repo') o con owner ('owner/mi-repo')."},
            "title": {"type": "string", "description": "Título del PR."},
            "head":  {"type": "string", "description": "Rama con los cambios (ej: 'feat/mi-feature')."},
            "base":  {"type": "string", "description": "Rama destino. Default: 'main'.", "default": "main"},
            "body":  {"type": "string", "description": "Descripción del PR (markdown).", "default": ""},
        },
        "required": ["repo", "title", "head"],
    },
    handler=_handle_github_create_pr,
    requires_confirmation=False,
))


registry.register(LocalTool(
    name="save_playbook",
    description=(
        "Guarda una secuencia de tools como playbook reutilizable. "
        "Cada paso es {label, tool, params}. "
        "Usalo cuando el usuario quiera guardar un flujo que acabas de ejecutar, "
        "o cuando te pida crear una automatización personalizada. "
        "Ejemplo de steps: [{\"label\": \"Leer inbox\", \"tool\": \"read_gmail_inbox\", \"params\": {\"max_results\": 10}}, ...]"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name":        {"type": "string", "description": "Nombre descriptivo del playbook."},
            "description": {"type": "string", "description": "Qué hace este flujo y cuándo usarlo."},
            "steps": {
                "type": "array",
                "description": "Lista de pasos en orden.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label":  {"type": "string", "description": "Nombre legible del paso."},
                        "tool":   {"type": "string", "description": "Nombre exacto de la tool."},
                        "params": {"type": "object", "description": "Parámetros para la tool."},
                    },
                    "required": ["label", "tool"],
                },
            },
            "tags": {"type": "array", "items": {"type": "string"}, "description": "Etiquetas opcionales."},
        },
        "required": ["name", "steps"],
    },
    handler=_handle_save_playbook,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="list_playbooks",
    description="Lista todos los playbooks guardados con su metadata (nombre, pasos, última ejecución).",
    input_schema={"type": "object", "properties": {}},
    handler=_handle_list_playbooks,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="get_playbook",
    description="Obtiene los detalles completos de un playbook, incluyendo todos sus pasos.",
    input_schema={
        "type": "object",
        "properties": {"playbook_id": {"type": "string"}},
        "required": ["playbook_id"],
    },
    handler=_handle_get_playbook,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="run_playbook",
    description=(
        "Ejecuta un playbook por su ID: carga los pasos y los devuelve como instrucciones "
        "para que los ejecutes en orden usando tus tools. "
        "Usá list_playbooks() primero si no sabés el ID."
    ),
    input_schema={
        "type": "object",
        "properties": {"playbook_id": {"type": "string"}},
        "required": ["playbook_id"],
    },
    handler=_handle_run_playbook,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="update_playbook",
    description="Actualiza un playbook existente (nombre, descripción, pasos o tags).",
    input_schema={
        "type": "object",
        "properties": {
            "playbook_id": {"type": "string"},
            "name":        {"type": "string"},
            "description": {"type": "string"},
            "steps":       {"type": "array", "items": {"type": "object"}},
            "tags":        {"type": "array", "items": {"type": "string"}},
        },
        "required": ["playbook_id"],
    },
    handler=_handle_update_playbook,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="delete_playbook",
    description="Elimina un playbook permanentemente.",
    input_schema={
        "type": "object",
        "properties": {"playbook_id": {"type": "string"}},
        "required": ["playbook_id"],
    },
    handler=_handle_delete_playbook,
    requires_confirmation=True,
))


# --- Chrome agent (Fase 8) ---

async def _handle_chrome_navigate(url: str, screenshot: bool = False) -> dict:
    from app.chrome.agent import ChromeAgent
    agent = ChromeAgent()
    result = await agent.navigate(url, take_screenshot=screenshot)
    return {
        "url": result.url,
        "title": result.title,
        "text": result.text_content,
        "screenshot_b64": result.screenshot_b64,
        "flagged": result.flagged,
        "flag_reason": result.flag_reason,
        "needs_login": result.needs_login,
        "error": result.error,
        "meta": result.meta,
    }


async def _handle_chrome_screenshot(url: str) -> dict:
    from app.chrome.agent import ChromeAgent
    agent = ChromeAgent()
    result = await agent.screenshot(url)
    return {
        "url": result.url,
        "title": result.title,
        "screenshot_b64": result.screenshot_b64,
        "flagged": result.flagged,
        "flag_reason": result.flag_reason,
        "error": result.error,
    }


registry.register(LocalTool(
    name="chrome_navigate",
    description=(
        "Navega a una URL en un browser headless y devuelve el texto visible de la página. "
        "Solo funciona con dominios autorizados (CHROME_ALLOWED_DOMAINS). "
        "Detecta automáticamente si el sitio requiere login. "
        "Útil para leer perfiles de Instagram, LinkedIn y otros sitios públicos."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL completa a navegar (debe ser de un dominio autorizado)."},
            "screenshot": {"type": "boolean", "default": False, "description": "Si true, incluye screenshot en base64 en la respuesta."},
        },
        "required": ["url"],
    },
    handler=_handle_chrome_navigate,
    requires_confirmation=False,
))

registry.register(LocalTool(
    name="chrome_screenshot",
    description=(
        "Captura una screenshot de una URL y la devuelve en base64. "
        "Solo funciona con dominios autorizados (CHROME_ALLOWED_DOMAINS)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL completa a capturar."},
        },
        "required": ["url"],
    },
    handler=_handle_chrome_screenshot,
    requires_confirmation=False,
))
