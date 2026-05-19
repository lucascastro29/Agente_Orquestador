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
                "items": {"type": "string",
                          "enum": ["objetivo_actual", "proyecto", "preferencia", "persona", "recordatorio", "nota_libre"]},
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
            "category": {
                "type": "string",
                "enum": ["objetivo_actual", "proyecto", "preferencia", "persona", "recordatorio", "nota_libre"],
            },
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
            "category": {"type": "string",
                         "enum": ["objetivo_actual", "proyecto", "preferencia", "persona", "recordatorio", "nota_libre"]},
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
