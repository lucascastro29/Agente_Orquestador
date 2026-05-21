from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Worker


class WorkerManager:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        agent_id: str,
        session_id: str,
        type: str,
        prompt: str,
        working_dir: str | None = None,
        notion_task_id: str | None = None,
        parent_id: str | None = None,
    ) -> Worker:
        worker = Worker(
            agent_id=agent_id,
            session_id=session_id,
            type=type,
            prompt=prompt,
            working_dir=working_dir,
            notion_task_id=notion_task_id,
            parent_id=parent_id,
            status="pending",
        )
        self.db.add(worker)
        await self.db.commit()
        await self.db.refresh(worker)
        return worker

    async def update_status(self, worker_id: str, status: str, **kwargs) -> Worker:
        result = await self.db.execute(select(Worker).where(Worker.id == worker_id))
        worker = result.scalar_one_or_none()
        if not worker:
            raise ValueError(f"Worker {worker_id} not found")
        worker.status = status
        for k, v in kwargs.items():
            setattr(worker, k, v)
        if status == "running" and not worker.started_at:
            worker.started_at = datetime.now(timezone.utc)
        if status in ("done", "failed", "cancelled", "no_credits") and not worker.finished_at:
            worker.finished_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(worker)
        return worker

    async def append_output(self, worker_id: str, chunk: str) -> None:
        result = await self.db.execute(select(Worker).where(Worker.id == worker_id))
        worker = result.scalar_one_or_none()
        if worker:
            worker.output = (worker.output or "") + chunk
            await self.db.commit()

    async def get_active(self) -> list[Worker]:
        result = await self.db.execute(
            select(Worker)
            .where(Worker.status.in_(["pending", "running", "waiting_input"]))
            .order_by(Worker.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_session(self, session_id: str) -> list[Worker]:
        result = await self.db.execute(
            select(Worker)
            .where(Worker.session_id == session_id)
            .order_by(Worker.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_all(self, limit: int = 50) -> list[Worker]:
        result = await self.db.execute(
            select(Worker).order_by(Worker.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, worker_id: str) -> Worker | None:
        result = await self.db.execute(select(Worker).where(Worker.id == worker_id))
        return result.scalar_one_or_none()

    async def retry(self, worker_id: str) -> "Worker | None":
        """Resetea un worker no_credits a pending para re-encolar."""
        result = await self.db.execute(select(Worker).where(Worker.id == worker_id))
        worker = result.scalar_one_or_none()
        if not worker or worker.status != "no_credits":
            return None
        worker.status = "pending"
        worker.error = None
        worker.output = None
        worker.result_summary = None
        worker.started_at = None
        worker.finished_at = None
        await self.db.commit()
        await self.db.refresh(worker)
        return worker

    async def cancel(self, worker_id: str) -> bool:
        result = await self.db.execute(select(Worker).where(Worker.id == worker_id))
        worker = result.scalar_one_or_none()
        if not worker or worker.status in ("done", "failed", "cancelled"):
            return False
        worker.status = "cancelled"
        worker.finished_at = datetime.now(timezone.utc)
        await self.db.commit()
        return True
