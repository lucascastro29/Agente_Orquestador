"""Registro de sub-agentes especializados."""
from dataclasses import dataclass, field


@dataclass
class SubAgentConfig:
    id: str
    model: str
    system_prompt: str
    allowed_tools: list[str]
    forbidden_tools: list[str]
    max_workers: int
    approval_policy: str  # "auto" | "confirm_writes" | "confirm_all"
    max_duration_minutes: int


SUB_AGENTS: dict[str, SubAgentConfig] = {
    "sub_dev": SubAgentConfig(
        id="sub_dev",
        model="claude-sonnet-4-6",
        system_prompt=(
            "Sos un dev senior especializado en implementación técnica. "
            "Tu objetivo es ejecutar tareas de código de manera autónoma y eficiente. "
            "Coordinás múltiples Claude Code sessions para completar objetivos complejos. "
            "Reportás progreso al orquestador regularmente. "
            "Ante bloqueantes técnicos, describís el problema con precisión antes de escalar."
        ),
        allowed_tools=[
            "run_claude_code", "get_workers_status", "cancel_worker",
            "get_memoria", "update_memoria",
            "notion_get_tasks", "notion_search", "notion_list_database", "notion_get_page",
        ],
        forbidden_tools=["create_subagent"],
        max_workers=5,
        approval_policy="confirm_writes",
        max_duration_minutes=120,
    ),
    "sub_analista": SubAgentConfig(
        id="sub_analista",
        model="claude-sonnet-4-6",
        system_prompt=(
            "Sos un analista de datos especializado en investigación y síntesis. "
            "Tu objetivo es investigar, analizar y generar reportes detallados. "
            "Usás Claude Code sessions para procesar datos y generar insights. "
            "Nunca modificás archivos de producción ni enviás datos a servicios externos."
        ),
        allowed_tools=[
            "run_claude_code", "get_workers_status",
            "get_memoria", "update_memoria",
            "notion_search", "notion_list_database", "notion_get_page",
        ],
        forbidden_tools=["create_subagent", "cancel_worker"],
        max_workers=3,
        approval_policy="auto",
        max_duration_minutes=60,
    ),
}


def get_subagent(subagent_type: str) -> SubAgentConfig:
    if subagent_type not in SUB_AGENTS:
        raise ValueError(
            f"Sub-agente desconocido: '{subagent_type}'. "
            f"Tipos válidos: {list(SUB_AGENTS.keys())}"
        )
    return SUB_AGENTS[subagent_type]
