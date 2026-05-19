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
