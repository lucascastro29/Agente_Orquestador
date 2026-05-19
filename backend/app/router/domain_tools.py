from dataclasses import dataclass


@dataclass
class DomainContext:
    tools: list[str] | None        # None = cargar todas
    memory_categories: list[str] | None  # None = cargar toda
    model_override: str | None = None    # None = usar el sugerido por el router


DOMAIN_CONTEXTS: dict[str, DomainContext] = {
    "consulta_simple": DomainContext(
        tools=[],
        memory_categories=["nota_libre"],
        model_override="claude-haiku-4-5-20251001",
    ),
    "notion_tasks": DomainContext(
        tools=["run_claude_code", "get_memoria", "update_memoria"],
        memory_categories=["proyecto", "objetivo_actual"],
    ),
    "coding": DomainContext(
        tools=["run_claude_code", "create_subagent", "get_memoria", "update_memoria", "search_memoria"],
        memory_categories=["proyecto"],
    ),
    "admin_email": DomainContext(
        tools=["get_memoria", "update_memoria"],
        memory_categories=["preferencia", "persona"],
    ),
    "admin_calendar": DomainContext(
        tools=["get_memoria", "update_memoria"],
        memory_categories=["preferencia", "recordatorio"],
    ),
    "analisis": DomainContext(
        tools=["run_claude_code", "get_memoria", "search_memoria"],
        memory_categories=["proyecto", "objetivo_actual"],
    ),
    "arquitectura": DomainContext(
        tools=None,
        memory_categories=None,
    ),
}


def get_domain_context(category: str) -> DomainContext:
    return DOMAIN_CONTEXTS.get(category, DomainContext(tools=None, memory_categories=None))
