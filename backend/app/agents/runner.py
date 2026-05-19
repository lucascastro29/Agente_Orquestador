import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import anthropic
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import AgentConfig
from app.config import settings
from app.costs.tracker import CostTracker
from app.db.models import Message, PendingApproval, Session as DBSession, ToolTrace
from app.memory.service import MemoryService
from app.security.validator import SecurityValidator
from app.tools.registry import registry


@dataclass
class RunResult:
    text: str = ""
    blocked: bool = False
    blocked_reason: str = ""
    pending_approval_id: str | None = None
    turn_cost: float = 0.0
    session_cost: float = 0.0
    cost_footer: str = ""
    cost_detail: dict = field(default_factory=dict)


class AgentRunner:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.memory_svc = MemoryService(db)
        self.cost_tracker = CostTracker(db)
        self.security = SecurityValidator(db)

    async def run(
        self,
        agent: AgentConfig,
        session_id: str,
        prior_messages: list[dict],
        user_message: str,
        channel: str = "web",
    ) -> RunResult:
        # Construir system param con memoria inyectada
        system_param = await self._build_system_param(agent)

        messages = list(prior_messages)
        messages.append({"role": "user", "content": user_message})

        tools = registry.to_anthropic_tools(agent.allowed_tools)

        accumulated_text = ""
        final_usage = None
        final_model = agent.model

        # Loop agéntico
        while True:
            response = await self.client.messages.create(
                model=agent.model,
                max_tokens=agent.max_tokens,
                system=system_param,
                messages=messages,
                tools=tools if tools else anthropic.NOT_GIVEN,
            )

            final_usage = response.usage
            final_model = response.model

            # Acumular texto de la respuesta
            for block in response.content:
                if hasattr(block, "text"):
                    accumulated_text += block.text

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                # Agregar respuesta del asistente al historial
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    tool_result = await self._execute_local_tool(
                        block, agent, session_id
                    )

                    # Si requiere aprobación, pausar el loop
                    if tool_result is None:
                        approval_id = await self._create_pending_approval(
                            session_id=session_id,
                            tool_use_id=block.id,
                            tool_name=block.name,
                            tool_input=block.input,
                        )
                        return RunResult(
                            text=accumulated_text,
                            pending_approval_id=approval_id,
                        )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(tool_result),
                    })

                messages.append({"role": "user", "content": tool_results})
                continue

            break

        # Calcular costo
        turn_cost = self.cost_tracker.calculate(final_model, final_usage) if final_usage else 0.0

        # Verificar límites
        limit_result = await self.cost_tracker.check_limits(
            session_id=session_id,
            turn_cost=turn_cost,
            max_session=settings.max_cost_per_session_usd,
            max_day=settings.max_cost_per_day_usd,
        )

        # Persistir mensaje del usuario y respuesta
        await self._persist_turn(
            session_id=session_id,
            user_message=user_message,
            response=response,
            model=final_model,
            cost_usd=turn_cost,
        )

        # Actualizar costo total de la sesión
        session_cost = await self._update_session_cost(session_id, turn_cost)

        # Armar footer según canal
        if channel == "telegram":
            footer = self.cost_tracker.format_footer_telegram(turn_cost, session_cost, final_usage)
        else:
            footer = ""

        cost_detail = self.cost_tracker.format_footer_web(turn_cost, session_cost, final_usage)

        if not limit_result.ok:
            accumulated_text += f"\n\n⚠️ {limit_result.reason}"

        return RunResult(
            text=accumulated_text + footer,
            turn_cost=turn_cost,
            session_cost=session_cost,
            cost_footer=footer,
            cost_detail=cost_detail,
        )

    async def _build_system_param(self, agent: AgentConfig) -> list[dict]:
        memory_entries = await self.memory_svc.get_relevant(limit=20)
        memory_text = self.memory_svc.format_for_prompt(memory_entries)

        system_text = agent.system_prompt
        if memory_text:
            system_text += f"\n\n{memory_text}"

        return [
            {
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    async def _execute_local_tool(
        self, block: Any, agent: AgentConfig, session_id: str
    ) -> Any | None:
        tool = registry.get(block.name)
        if tool is None:
            return {"error": f"Tool '{block.name}' no encontrada en el registry"}

        # Validar con SecurityValidator
        validation = self.security.validate_tool_call(
            agent_id=agent.id,
            tool_name=block.name,
            tool_input=block.input,
            allowed_tools=agent.allowed_tools or registry.names(),
        )
        if not validation.allowed:
            await self.security.log_event(
                severity="warning",
                event_type="tool_blocked",
                source="tool_call",
                raw_content=str(block.input),
                action_taken="blocked",
                agent_id=agent.id,
                session_id=session_id,
            )
            return {"error": validation.reason}

        # Si requiere confirmación, señalizar con None para pausar
        if tool.requires_confirmation:
            return None

        start = time.monotonic()
        error_str = None
        output = None

        try:
            # Inyectar memory_service para tools de memoria
            if block.name in ("get_memoria", "update_memoria", "delete_memoria", "search_memoria"):
                output = await tool.handler(self.memory_svc, **block.input)
            else:
                output = await tool.handler(**block.input)

            # Sanitizar output
            sanitized = self.security.sanitize_tool_output(str(output))
            if sanitized.flagged:
                await self.security.log_event(
                    severity="warning",
                    event_type="injection_in_tool_output",
                    source="tool_output",
                    raw_content=sanitized.content[:500],
                    action_taken="flagged",
                    agent_id=agent.id,
                    session_id=session_id,
                    pattern=sanitized.pattern,
                )
        except Exception as exc:
            error_str = str(exc)
            output = {"error": error_str}

        duration_ms = int((time.monotonic() - start) * 1000)

        trace = ToolTrace(
            session_id=session_id,
            tool_name=block.name,
            tool_input=block.input,
            tool_output=output if isinstance(output, dict) else {"result": str(output)},
            error=error_str,
            duration_ms=duration_ms,
        )
        self.db.add(trace)
        await self.db.commit()

        return output

    async def _create_pending_approval(
        self, session_id: str, tool_use_id: str, tool_name: str, tool_input: dict
    ) -> str:
        approval = PendingApproval(
            session_id=session_id,
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            tool_input=tool_input,
            status="pending",
        )
        self.db.add(approval)
        await self.db.commit()
        await self.db.refresh(approval)
        return approval.id

    async def _persist_turn(
        self,
        session_id: str,
        user_message: str,
        response: Any,
        model: str,
        cost_usd: float,
    ) -> None:
        # Posición del próximo mensaje
        result = await self.db.execute(
            select(func.count(Message.id)).where(Message.session_id == session_id)
        )
        base_pos = result.scalar_one() or 0

        user_msg = Message(
            session_id=session_id,
            position=base_pos,
            role="user",
            content=[{"type": "text", "text": user_message}],
        )
        self.db.add(user_msg)

        content_blocks = [
            b.model_dump() if hasattr(b, "model_dump") else {"type": "text", "text": str(b)}
            for b in response.content
        ]
        usage = response.usage
        assistant_msg = Message(
            session_id=session_id,
            position=base_pos + 1,
            role="assistant",
            content=content_blocks,
            model=model,
            stop_reason=response.stop_reason,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", None),
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None),
            cost_usd=cost_usd,
        )
        self.db.add(assistant_msg)
        await self.db.commit()

    async def _update_session_cost(self, session_id: str, turn_cost: float) -> float:
        result = await self.db.execute(
            select(DBSession).where(DBSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.total_cost_usd = (session.total_cost_usd or 0.0) + turn_cost
            session.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            return session.total_cost_usd
        return turn_cost
