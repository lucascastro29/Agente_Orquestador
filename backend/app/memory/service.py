from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Memory


class MemoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_relevant(
        self, limit: int = 20, categories: list[str] | None = None
    ) -> list[Memory]:
        q = select(Memory).order_by(Memory.updated_at.desc())
        if categories:
            q = q.where(Memory.category.in_(categories))
        q = q.limit(limit)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def upsert(self, key: str, value: dict, category: str) -> Memory:
        result = await self.db.execute(
            select(Memory).where(Memory.key == key, Memory.category == category)
        )
        entry = result.scalar_one_or_none()
        if entry:
            entry.value = value
            entry.updated_at = datetime.now(timezone.utc)
        else:
            entry = Memory(key=key, value=value, category=category)
            self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def delete(self, key: str, category: str) -> bool:
        result = await self.db.execute(
            delete(Memory).where(Memory.key == key, Memory.category == category)
        )
        await self.db.commit()
        return result.rowcount > 0

    async def delete_by_id(self, memory_id: str) -> bool:
        result = await self.db.execute(
            delete(Memory).where(Memory.id == memory_id)
        )
        await self.db.commit()
        return result.rowcount > 0

    async def search(self, query: str, limit: int = 10) -> list[Memory]:
        """Búsqueda simple por substring en key (para Fase 1; Fase 5+ puede usar embeddings)."""
        q = (
            select(Memory)
            .where(Memory.key.ilike(f"%{query}%"))
            .order_by(Memory.updated_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(q)
        return list(result.scalars().all())

    def format_for_prompt(self, entries: list[Memory]) -> str:
        if not entries:
            return ""
        lines = ["## Memoria del orquestador\n"]
        by_category: dict[str, list[Memory]] = {}
        for e in entries:
            by_category.setdefault(e.category, []).append(e)
        for cat, items in by_category.items():
            lines.append(f"### {cat}")
            for item in items:
                val = item.value.get("text") or str(item.value)
                lines.append(f"- **{item.key}**: {val}")
            lines.append("")
        return "\n".join(lines)
