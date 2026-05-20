from dataclasses import dataclass


@dataclass
class DomainContext:
    tools: list[str] | None              # None = cargar todas
    memory_categories: list[str] | None  # None = cargar toda
    model_override: str | None = None    # None = usar el sugerido por el router
    use_mcp: bool = False                # True = inyectar MCP servers según categoría


DOMAIN_CONTEXTS: dict[str, DomainContext] = {
    "consulta_simple": DomainContext(
        tools=["get_memoria", "get_workers_status", "notion_search"],
        memory_categories=["nota_libre"],
        model_override="claude-haiku-4-5-20251001",
    ),
    "notion_tasks": DomainContext(
        tools=[
            "notion_search", "notion_list_database", "notion_get_page",
            "notion_get_tasks", "notion_create_task", "run_claude_code",
            "get_memoria", "update_memoria",
        ],
        memory_categories=["proyecto", "objetivo_actual"],
    ),
    "coding": DomainContext(
        tools=["run_claude_code", "create_subagent", "get_memoria", "update_memoria", "search_memoria"],
        memory_categories=["proyecto"],
    ),
    "admin_email": DomainContext(
        tools=["read_gmail_inbox", "get_memoria", "update_memoria", "notion_create_task"],
        memory_categories=["preferencia", "persona"],
        use_mcp=True,
    ),
    "admin_calendar": DomainContext(
        tools=["read_calendar_events", "get_memoria", "update_memoria", "notion_create_task"],
        memory_categories=["preferencia", "recordatorio"],
        use_mcp=True,
    ),
    "tareas_programadas": DomainContext(
        tools=[
            "schedule_task", "list_scheduled_tasks", "delete_scheduled_task", "toggle_scheduled_task",
            "read_gmail_inbox", "read_calendar_events",
            "notion_search", "notion_create_task", "notion_update_task",
            "run_claude_code", "create_subagent",
            "get_memoria", "update_memoria",
        ],
        memory_categories=["proyecto", "objetivo_actual", "recordatorio"],
        use_mcp=True,
    ),
    "analisis": DomainContext(
        tools=[
            "run_claude_code", "get_memoria", "search_memoria",
            "notion_search", "notion_list_database", "notion_get_page",
        ],
        memory_categories=["proyecto", "objetivo_actual"],
    ),
    "arquitectura": DomainContext(
        tools=None,
        memory_categories=None,
    ),
}


def get_domain_context(category: str) -> DomainContext:
    return DOMAIN_CONTEXTS.get(category, DomainContext(tools=None, memory_categories=None))
