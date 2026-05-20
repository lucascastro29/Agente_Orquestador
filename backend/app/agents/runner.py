import json
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import anthropic
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.config import AgentConfig, ORCHESTRATOR_SYSTEM, get_agent
from app.config import settings
from app.costs.tracker import CostTracker
from app.db.models import Message, PendingApproval, Session as DBSession, ToolTrace
from app.memory.service import MemoryService
from app.router.classifier import MessageRouter, RouteResult
from app.router.domain_tools import get_domain_context
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
        # Importación lazy para evitar ciclo circular
        from app.workers.manager import WorkerManager
        self.worker_mgr = WorkerManager(db)

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
            response = await self._api_create(
                agent=agent,
                system=system_param,
                messages=messages,
                tools=tools,
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

    # --- Router inteligente (Fase 2) ---

    async def run_routed(
        self,
        message: str,
        session_id: str,
        prior_messages: list[dict],
        channel: str = "web",
    ) -> RunResult:
        """Clasifica el mensaje y despacha al agente/modelo adecuado."""
        route = await MessageRouter().classify(message)

        # Bloquear por seguridad antes de crear nada
        if route.security_flag == "block":
            await self._handle_security_block(message, session_id, route)
            return RunResult(blocked=True, blocked_reason="Mensaje bloqueado por política de seguridad.")

        # Consulta simple → Haiku directo, sin tools, sin loop agéntico completo
        if route.complexity == "low" and route.suggested_model == "haiku":
            return await self._run_direct_haiku(message, session_id, prior_messages, route, channel)

        # Resto → orquestador con contexto filtrado
        filtered_agent = self._build_filtered_agent(route)
        return await self.run(
            agent=filtered_agent,
            session_id=session_id,
            prior_messages=prior_messages,
            user_message=message,
            channel=channel,
        )

    async def _run_direct_haiku(
        self,
        message: str,
        session_id: str,
        prior_messages: list[dict],
        route: RouteResult,
        channel: str,
    ) -> RunResult:
        model = "claude-haiku-4-5-20251001"
        ctx = get_domain_context(route.category)

        # Memoria filtrada para consulta simple
        memory_entries = await self.memory_svc.get_relevant(
            limit=10, categories=ctx.memory_categories
        )
        memory_text = self.memory_svc.format_for_prompt(memory_entries)
        system_text = ORCHESTRATOR_SYSTEM
        if memory_text:
            system_text += f"\n\n{memory_text}"

        messages = list(prior_messages)
        messages.append({"role": "user", "content": message})

        # Incluir tools del dominio si las hay (permite get_workers_status en consulta_simple)
        tools = registry.to_anthropic_tools(ctx.tools) if ctx.tools else []

        create_kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=1024,
            system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        if tools:
            create_kwargs["tools"] = tools

        # Si hay tools, usar el loop completo para manejar tool_use
        if tools:
            agent = self._build_filtered_agent(route)
            agent.model = model
            agent.max_tokens = 1024
            return await self.run(
                agent=agent,
                session_id=session_id,
                prior_messages=prior_messages,
                user_message=message,
                channel=channel,
            )

        response = await self.client.messages.create(**create_kwargs)

        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        turn_cost = self.cost_tracker.calculate(model, response.usage)

        await self._persist_turn(
            session_id=session_id,
            user_message=message,
            response=response,
            model=model,
            cost_usd=turn_cost,
        )
        session_cost = await self._update_session_cost(session_id, turn_cost)

        footer = self.cost_tracker.format_footer_telegram(turn_cost, session_cost, response.usage) if channel == "telegram" else ""
        cost_detail = self.cost_tracker.format_footer_web(turn_cost, session_cost, response.usage)

        return RunResult(
            text=text + footer,
            turn_cost=turn_cost,
            session_cost=session_cost,
            cost_footer=footer,
            cost_detail=cost_detail,
        )

    def _build_filtered_agent(self, route: RouteResult) -> AgentConfig:
        from app.agents.config import AgentConfig, build_mcp_servers_for_category
        ctx = get_domain_context(route.category)

        model_map = {
            "haiku": "claude-haiku-4-5-20251001",
            "sonnet": "claude-sonnet-4-6",
            "opus": "claude-opus-4-7",
        }
        model = ctx.model_override or model_map.get(route.suggested_model, "claude-sonnet-4-6")

        # tools: None en el contexto = todas; lista vacía = ninguna
        if ctx.tools is None:
            allowed_tools = None
        elif len(ctx.tools) == 0:
            allowed_tools = []
        else:
            allowed_tools = ctx.tools

        mcp_servers = build_mcp_servers_for_category(route.category) if ctx.use_mcp else []

        return AgentConfig(
            id="orchestrator",
            model=model,
            system_prompt=ORCHESTRATOR_SYSTEM,
            allowed_tools=allowed_tools,
            mcp_servers=mcp_servers,
            max_tokens=8096,
        )

    async def _handle_security_block(
        self, message: str, session_id: str, route: RouteResult
    ) -> None:
        await self.security.log_event(
            severity="critical",
            event_type="injection_attempt",
            source="user_message",
            raw_content=message,
            action_taken="blocked",
            session_id=session_id if session_id else None,
            pattern=f"router:security_flag=block category={route.category}",
        )

    # --- Streaming (Fase 3) ---

    async def stream_run_routed(
        self,
        message: str,
        session_id: str,
        prior_messages: list[dict],
    ) -> AsyncGenerator[str, None]:
        """Clasifica y despacha, emitiendo eventos SSE."""
        route = await MessageRouter().classify(message)

        if route.security_flag == "block":
            await self._handle_security_block(message, session_id, route)
            yield _sse({"type": "security_alert", "severity": "critical", "fragment": message[:200]})
            yield _sse({"type": "done"})
            return

        agent = self._build_filtered_agent(route) if route.complexity != "low" else None
        model = "claude-haiku-4-5-20251001" if route.complexity == "low" else (agent.model if agent else "claude-sonnet-4-6")
        ctx = get_domain_context(route.category)

        # Memoria según dominio
        memory_entries = await self.memory_svc.get_relevant(
            limit=10 if route.complexity == "low" else 20,
            categories=ctx.memory_categories,
        )
        memory_text = self.memory_svc.format_for_prompt(memory_entries)
        system_text = ORCHESTRATOR_SYSTEM + (f"\n\n{memory_text}" if memory_text else "")
        system_param = [{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}]

        tools = registry.to_anthropic_tools(agent.allowed_tools if agent else [])
        messages = list(prior_messages)
        messages.append({"role": "user", "content": message})
        max_tokens = 1024 if route.complexity == "low" else 8096

        accumulated_text = ""
        final_usage = None
        final_model = model

        async for event in self._stream_loop(
            model=model,
            system_param=system_param,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            agent=agent,
            session_id=session_id,
        ):
            if event.get("type") == "_text":
                accumulated_text += event["text"]
                yield _sse({"type": "text_delta", "text": event["text"]})
            elif event.get("type") == "_usage":
                final_usage = event["usage"]
                final_model = event["model"]
            elif event.get("type") == "_memory_updated":
                yield _sse({"type": "memory_updated", "key": event["key"], "category": event["category"]})
            elif event.get("type") in ("tool_use_start", "tool_use_result", "approval_needed"):
                yield _sse(event)

        # Costo y persistencia
        turn_cost = self.cost_tracker.calculate(final_model, final_usage) if final_usage else 0.0
        await self._persist_turn_streaming(
            session_id=session_id,
            user_message=message,
            assistant_text=accumulated_text,
            model=final_model,
            usage=final_usage,
            cost_usd=turn_cost,
        )
        session_cost = await self._update_session_cost(session_id, turn_cost)

        if final_usage:
            cost_detail = self.cost_tracker.format_footer_web(turn_cost, session_cost, final_usage)
            yield _sse({"type": "cost_update", "turn_cost": turn_cost, "session_cost": session_cost, "tokens": cost_detail})

        yield _sse({"type": "done"})

    async def _stream_loop(
        self,
        model: str,
        system_param: list[dict],
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
        agent: AgentConfig | None,
        session_id: str,
    ) -> AsyncGenerator[dict, None]:
        while True:
            kwargs: dict[str, Any] = dict(
                model=model,
                max_tokens=max_tokens,
                system=system_param,
                messages=messages,
            )
            if tools:
                kwargs["tools"] = tools

            # Acumular el mensaje completo para el historial
            tool_uses: list[Any] = []
            current_tool_input_json = ""
            current_tool_name = ""
            current_tool_id = ""
            final_stop_reason = "end_turn"
            final_usage_obj = None
            final_model_name = model

            async with self.client.messages.stream(**kwargs) as stream:
                async for raw_event in stream:
                    etype = raw_event.type

                    if etype == "content_block_start":
                        block = raw_event.content_block
                        if block.type == "tool_use":
                            current_tool_name = block.name
                            current_tool_id = block.id
                            current_tool_input_json = ""
                            yield {"type": "tool_use_start", "tool_name": block.name, "tool_input": {}}

                    elif etype == "content_block_delta":
                        delta = raw_event.delta
                        if delta.type == "text_delta":
                            yield {"type": "_text", "text": delta.text}
                        elif delta.type == "input_json_delta":
                            current_tool_input_json += delta.partial_json

                    elif etype == "content_block_stop":
                        if current_tool_name:
                            try:
                                parsed = json.loads(current_tool_input_json) if current_tool_input_json else {}
                            except json.JSONDecodeError:
                                parsed = {}
                            tool_uses.append(
                                type("ToolUseBlock", (), {
                                    "type": "tool_use",
                                    "id": current_tool_id,
                                    "name": current_tool_name,
                                    "input": parsed,
                                })()
                            )
                            current_tool_name = ""
                            current_tool_input_json = ""

                    elif etype == "message_delta":
                        if hasattr(raw_event, "delta"):
                            final_stop_reason = getattr(raw_event.delta, "stop_reason", "end_turn") or "end_turn"
                        if hasattr(raw_event, "usage"):
                            final_usage_obj = raw_event.usage

                    elif etype == "message_start":
                        if hasattr(raw_event, "message"):
                            final_model_name = getattr(raw_event.message, "model", model)
                            if hasattr(raw_event.message, "usage"):
                                final_usage_obj = raw_event.message.usage

                if final_usage_obj is None:
                    msg = await stream.get_final_message()
                    final_usage_obj = msg.usage
                    final_stop_reason = msg.stop_reason or "end_turn"
                    final_model_name = msg.model

            yield {"type": "_usage", "usage": final_usage_obj, "model": final_model_name}

            if final_stop_reason != "tool_use" or not tool_uses:
                break

            # Ejecutar tools y continuar el loop
            messages.append({"role": "assistant", "content": [
                {"type": "tool_use", "id": t.id, "name": t.name, "input": t.input}
                for t in tool_uses
            ]})

            tool_results = []
            for tool_block in tool_uses:
                result = await self._execute_local_tool(tool_block, agent or _dummy_agent(), session_id)

                if result is None:
                    # Requiere aprobación
                    approval_id = await self._create_pending_approval(
                        session_id=session_id,
                        tool_use_id=tool_block.id,
                        tool_name=tool_block.name,
                        tool_input=tool_block.input,
                    )
                    yield {"type": "approval_needed", "approval_id": approval_id,
                           "tool_name": tool_block.name, "tool_input": tool_block.input}
                    tool_results.append({"type": "tool_result", "tool_use_id": tool_block.id,
                                         "content": "Pendiente de aprobación del usuario."})
                    continue

                yield {"type": "tool_use_result", "tool_name": tool_block.name, "output": result}

                # Detectar si la tool actualizó memoria
                if tool_block.name == "update_memoria" and isinstance(result, dict) and result.get("ok"):
                    yield {"type": "_memory_updated", "key": result.get("key", ""), "category": result.get("category", "")}

                tool_results.append({"type": "tool_result", "tool_use_id": tool_block.id,
                                      "content": json.dumps(result, ensure_ascii=False)})

            messages.append({"role": "user", "content": tool_results})
            tool_uses = []

    async def _api_create(
        self,
        agent: AgentConfig,
        system: list[dict],
        messages: list[dict],
        tools: list[dict],
    ) -> Any:
        """Wrapper que usa MCP connector (beta) si el agente tiene mcp_servers."""
        kwargs: dict[str, Any] = dict(
            model=agent.model,
            max_tokens=agent.max_tokens,
            system=system,
            messages=messages,
        )

        if agent.mcp_servers:
            # Formato nuevo: mcp-client-2025-11-20
            # tools locales + mcp_toolset por cada servidor MCP
            combined_tools: list[dict] = list(tools)
            for srv in agent.mcp_servers:
                combined_tools.append({
                    "type": "mcp_toolset",
                    "mcp_server_name": srv["name"],
                })
            if combined_tools:
                kwargs["tools"] = combined_tools
            try:
                return await self.client.beta.messages.create(
                    **kwargs,
                    mcp_servers=agent.mcp_servers,
                    betas=["mcp-client-2025-11-20"],
                )
            except Exception:
                # Degradar: quitar mcp_toolset entries y llamar sin MCP
                kwargs["tools"] = tools if tools else []

        if tools:
            kwargs["tools"] = tools
        elif "tools" in kwargs:
            del kwargs["tools"]

        return await self.client.messages.create(**kwargs)

    # --- Watcher events (Fase 6) ---

    async def receive_watcher_event(self, event_type: str, data: dict) -> str | None:
        """Crea una sesión interna y corre el orquestador con el evento del watcher."""
        from app.agents.config import ORCHESTRATOR
        from app.db.models import Session as DBSession

        session = DBSession(
            agent_id="orchestrator",
            channel="watcher",
            external_chat_id=settings.telegram_allowed_chat_id or None,
            title=f"watcher:{event_type}",
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        if event_type == "mail":
            msg = (
                f"[EVENTO WATCHER — MAIL NUEVO]\n"
                f"De: {data.get('from', '?')}\n"
                f"Asunto: {data.get('subject', '?')}\n"
                f"Extracto: {data.get('snippet', '')}\n\n"
                f"Decidí si vale la pena notificarme. Si sí, respondé con un resumen conciso."
            )
        elif event_type == "calendar":
            msg = (
                f"[EVENTO WATCHER — CALENDARIO]\n"
                f"Evento: {data.get('title', '?')}\n"
                f"Hora: {data.get('time', '?')}\n"
                f"Asistentes: {data.get('attendees', '')}\n\n"
                f"Decidí si vale la pena notificarme. Si sí, respondé con un recordatorio conciso."
            )
        else:
            msg = f"[EVENTO WATCHER — {event_type.upper()}]\n{data}"

        result = await self.run(
            agent=ORCHESTRATOR,
            session_id=session.id,
            prior_messages=[],
            user_message=msg,
            channel="telegram",
        )
        return result.text if not result.blocked else None

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
            # Inyectar dependencias según la tool
            if block.name in ("get_memoria", "update_memoria", "delete_memoria", "search_memoria"):
                output = await tool.handler(self.memory_svc, **block.input)
            elif block.name in ("run_claude_code", "get_workers_status", "cancel_worker", "create_subagent"):
                kwargs = dict(block.input)
                if block.name in ("run_claude_code", "create_subagent") and "session_id" not in kwargs:
                    kwargs["session_id"] = session_id
                output = await tool.handler(self.worker_mgr, **kwargs)
            elif block.name in ("schedule_task", "list_scheduled_tasks", "delete_scheduled_task", "toggle_scheduled_task"):
                output = await tool.handler(self.db, **block.input)
            elif block.name == "remember_session":
                output = await tool.handler(self.db, session_id, **block.input)
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

    async def _persist_turn_streaming(
        self,
        session_id: str,
        user_message: str,
        assistant_text: str,
        model: str,
        usage: Any,
        cost_usd: float,
    ) -> None:
        result = await self.db.execute(
            select(func.count(Message.id)).where(Message.session_id == session_id)
        )
        base_pos = result.scalar_one() or 0

        self.db.add(Message(
            session_id=session_id,
            position=base_pos,
            role="user",
            content=[{"type": "text", "text": user_message}],
        ))
        self.db.add(Message(
            session_id=session_id,
            position=base_pos + 1,
            role="assistant",
            content=[{"type": "text", "text": assistant_text}],
            model=model,
            stop_reason="end_turn",
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", None) if usage else None,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", None) if usage else None,
            cost_usd=cost_usd,
        ))
        await self.db.commit()

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


# --- Helpers de módulo ---

def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _dummy_agent() -> "AgentConfig":
    from app.agents.config import AgentConfig, ORCHESTRATOR_SYSTEM
    return AgentConfig(id="orchestrator", model="claude-sonnet-4-6", system_prompt=ORCHESTRATOR_SYSTEM)
