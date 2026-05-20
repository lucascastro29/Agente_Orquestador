"""Celery tasks para ejecutar Claude Code en background."""
import asyncio
import subprocess
from datetime import datetime, timezone

from app.worker import celery_app


def _run_sync(coro):
    """Ejecuta una coroutine desde contexto síncrono (Celery worker)."""
    return asyncio.run(coro)


async def _update_worker(worker_id: str, **kwargs):
    from app.db.session import AsyncSessionLocal
    from app.workers.manager import WorkerManager
    async with AsyncSessionLocal() as db:
        mgr = WorkerManager(db)
        await mgr.update_status(worker_id, kwargs.pop("status"), **kwargs)


async def _append_output(worker_id: str, chunk: str):
    from app.db.session import AsyncSessionLocal
    from app.workers.manager import WorkerManager
    async with AsyncSessionLocal() as db:
        mgr = WorkerManager(db)
        await mgr.append_output(worker_id, chunk)


async def _notify_telegram(session_id: str, text: str):
    """Notifica al usuario por Telegram si la sesión tiene chat_id asociado."""
    from app.db.session import AsyncSessionLocal
    from app.db.models import Session as DBSession
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(DBSession).where(DBSession.id == session_id))
        session = result.scalar_one_or_none()
        if session and session.channel == "telegram" and session.external_chat_id:
            from app.telegram.client import send_message
            await send_message(session.external_chat_id, text)


async def _sync_notion_complete(notion_task_id: str, result_summary: str, cost_usd: float):
    from app.notion.task_sync import NotionTaskSync
    sync = NotionTaskSync()
    try:
        await sync.complete_task(notion_task_id, result_summary, cost_usd)
    except Exception as exc:
        print(f"[notion] Error al completar tarea {notion_task_id}: {exc}")


@celery_app.task(name="workers.execute_claude_code", bind=True)
def execute_claude_code(self, worker_id: str, prompt: str, working_dir: str):
    _run_sync(_execute_claude_code_async(worker_id, prompt, working_dir))


async def _execute_claude_code_async(worker_id: str, prompt: str, working_dir: str):
    from app.db.session import AsyncSessionLocal
    from app.workers.manager import WorkerManager

    # Recuperar datos del worker
    async with AsyncSessionLocal() as db:
        mgr = WorkerManager(db)
        worker = await mgr.get_by_id(worker_id)
        if not worker:
            return
        notion_task_id = worker.notion_task_id
        session_id = worker.session_id

    await _update_worker(worker_id, status="running")

    try:
        import os
        env = os.environ.copy()
        # Claude Code usa ANTHROPIC_API_KEY del entorno
        proc = subprocess.run(
            ["claude", "--print", prompt],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=1800,
            env=env,
        )
        output = proc.stdout or ""
        stderr = proc.stderr or ""
        if stderr:
            output += f"\n\n[stderr]\n{stderr}"

        success = proc.returncode == 0
        result_summary = output[:500] if output else "(sin output)"

        await _update_worker(
            worker_id,
            status="done" if success else "failed",
            output=output,
            result_summary=result_summary,
            error=None if success else f"returncode={proc.returncode}",
        )

        # Actualizar Notion si aplica
        if notion_task_id:
            await _sync_notion_complete(notion_task_id, result_summary, cost_usd=0.0)

        # Notificar al usuario
        icon = "✅" if success else "❌"
        msg = f"{icon} Worker terminó\n\n<b>Prompt:</b> {prompt[:100]}…\n\n<b>Resultado:</b> {result_summary[:300]}"
        await _notify_telegram(session_id, msg)

    except subprocess.TimeoutExpired:
        await _update_worker(worker_id, status="failed", error="Timeout (30 min)")
        await _notify_telegram(session_id, f"⏱ Worker {worker_id[:8]} cancelado por timeout.")
    except FileNotFoundError:
        # claude CLI no instalado — marcar failed con mensaje claro
        await _update_worker(
            worker_id,
            status="failed",
            error="claude CLI no encontrado en PATH. Instalá Claude Code en el container.",
        )
        await _notify_telegram(session_id, f"⚠️ Worker {worker_id[:8]} falló: claude CLI no disponible en este entorno.")
    except Exception as exc:
        await _update_worker(worker_id, status="failed", error=str(exc))
        await _notify_telegram(session_id, f"❌ Worker {worker_id[:8]} falló: {exc}")


@celery_app.task(name="workers.run_due_scheduled_tasks")
def run_due_scheduled_tasks() -> None:
    asyncio.run(_run_due_scheduled_tasks_async())


async def _run_due_scheduled_tasks_async() -> None:
    from datetime import datetime, timezone
    from croniter import croniter
    from app.db.session import AsyncSessionLocal
    from app.db.models import ScheduledTask
    from sqlalchemy import select

    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScheduledTask)
            .where(ScheduledTask.enabled.is_(True))
            .where(ScheduledTask.next_run_at <= now)
        )
        due_tasks = list(result.scalars().all())

    for task in due_tasks:
        error_str = None
        try:
            await _execute_scheduled_task_action(task.id, task.action_type, task.action_config)
        except Exception as exc:
            error_str = str(exc)

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(ScheduledTask).where(ScheduledTask.id == task.id))
            t = result.scalar_one_or_none()
            if t:
                t.last_run_at = now
                t.run_count = (t.run_count or 0) + 1
                t.last_error = error_str
                try:
                    itr = croniter(t.cron_expr, now)
                    t.next_run_at = itr.get_next(datetime)
                except Exception:
                    t.enabled = False
                await db.commit()


async def _execute_scheduled_task_action(task_id: str, action_type: str, action_config: dict) -> None:
    from app.db.session import AsyncSessionLocal
    from app.agents.runner import AgentRunner
    from app.db.models import Session as DBSession

    if action_type == "message":
        message = action_config.get("message", "")
        if not message:
            return
        async with AsyncSessionLocal() as db:
            session = DBSession(agent_id="orchestrator", channel="scheduled", title=f"scheduled:{task_id[:8]}")
            db.add(session)
            await db.commit()
            await db.refresh(session)
            runner = AgentRunner(db)
            result = await runner.run_routed(
                message=message,
                session_id=session.id,
                prior_messages=[],
                channel="telegram",
            )
        if result.text:
            from app.config import settings
            from app.telegram.client import send_message
            if settings.telegram_allowed_chat_id:
                await send_message(settings.telegram_allowed_chat_id, result.text)

    elif action_type == "run_claude_code":
        prompt = action_config.get("prompt", "")
        working_dir = action_config.get("working_dir", "")
        if not prompt or not working_dir:
            return
        async with AsyncSessionLocal() as db:
            session = DBSession(agent_id="orchestrator", channel="scheduled", title=f"cc_scheduled:{task_id[:8]}")
            db.add(session)
            await db.commit()
            await db.refresh(session)
            from app.workers.manager import WorkerManager
            mgr = WorkerManager(db)
            worker = await mgr.create(
                agent_id="orchestrator",
                session_id=session.id,
                type="claude_code",
                prompt=prompt,
                working_dir=working_dir,
            )
        execute_claude_code.delay(worker.id, prompt, working_dir)

    elif action_type == "create_subagent":
        sub_type = action_config.get("type", "sub_dev")
        name = action_config.get("name", "sub_programado")
        objective = action_config.get("objective", "")
        working_dir = action_config.get("working_dir")
        if not objective:
            return
        async with AsyncSessionLocal() as db:
            session = DBSession(agent_id=sub_type, channel="scheduled", title=f"sub_scheduled:{task_id[:8]}")
            db.add(session)
            await db.commit()
            await db.refresh(session)
            from app.workers.manager import WorkerManager
            mgr = WorkerManager(db)
            worker = await mgr.create(
                agent_id=sub_type,
                session_id=session.id,
                type="subagent",
                prompt=f"[{name}] {objective}",
                working_dir=working_dir,
            )
        execute_subagent.delay(worker.id, sub_type, objective, working_dir, session.id)


@celery_app.task(name="workers.execute_subagent", bind=True)
def execute_subagent(self, worker_id: str, subagent_type: str, objective: str,
                     working_dir: str | None, session_id: str):
    _run_sync(_execute_subagent_async(worker_id, subagent_type, objective, working_dir, session_id))


async def _execute_subagent_async(worker_id: str, subagent_type: str, objective: str,
                                   working_dir: str | None, session_id: str):
    from app.agents.subagent_registry import get_subagent
    from app.agents.config import AgentConfig
    from app.agents.runner import AgentRunner
    from app.db.session import AsyncSessionLocal

    await _update_worker(worker_id, status="running")

    try:
        sub_cfg = get_subagent(subagent_type)

        full_objective = objective
        if working_dir:
            full_objective = f"{objective}\n\nDirectorio de trabajo: {working_dir}"

        agent = AgentConfig(
            id=sub_cfg.id,
            model=sub_cfg.model,
            system_prompt=sub_cfg.system_prompt,
            allowed_tools=sub_cfg.allowed_tools,
            approval_policy=sub_cfg.approval_policy,
            max_tokens=8096,
        )

        async with AsyncSessionLocal() as db:
            runner = AgentRunner(db)
            result = await runner.run(
                agent=agent,
                session_id=session_id,
                prior_messages=[],
                user_message=full_objective,
            )

        output = result.text or "(sin output)"
        await _update_worker(
            worker_id,
            status="done",
            output=output,
            result_summary=output[:500],
        )
        msg = f"✅ Sub-agente {subagent_type} terminó\n\n{output[:400]}"
        await _notify_telegram(session_id, msg)

    except Exception as exc:
        await _update_worker(worker_id, status="failed", error=str(exc))
        await _notify_telegram(session_id, f"❌ Sub-agente {worker_id[:8]} falló: {exc}")
