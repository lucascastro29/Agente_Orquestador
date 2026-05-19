"""Integración con Notion para leer y actualizar tareas etiquetadas."""
from dataclasses import dataclass

import httpx

from app.config import settings

_BASE = "https://api.notion.com/v1"
_VERSION = "2022-06-28"


@dataclass
class NotionTask:
    id: str
    title: str
    label: str
    status: str
    url: str


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.notion_api_token}",
        "Notion-Version": _VERSION,
        "Content-Type": "application/json",
    }


class NotionTaskSync:

    async def _search_database(self, board_name: str) -> str | None:
        """Encuentra el ID de una base de datos Notion por nombre."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{_BASE}/search",
                headers=_headers(),
                json={"query": board_name, "filter": {"property": "object", "value": "database"}},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            for r in results:
                title_parts = r.get("title", [])
                title = "".join(p.get("plain_text", "") for p in title_parts)
                if title.strip().lower() == board_name.strip().lower():
                    return r["id"]
        return None

    async def get_tasks_by_label(self, board: str, label: str) -> list[NotionTask]:
        """Lee tareas de un tablero filtradas por etiqueta."""
        if board not in settings.notion_watched_boards:
            raise PermissionError(f"Tablero '{board}' no está en NOTION_WATCHED_BOARDS")

        db_id = await self._search_database(board)
        if not db_id:
            raise ValueError(f"Tablero '{board}' no encontrado en Notion")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{_BASE}/databases/{db_id}/query",
                headers=_headers(),
                json={
                    "filter": {
                        "or": [
                            {"property": "Tags",   "multi_select": {"contains": label}},
                            {"property": "Label",  "select":       {"equals": label}},
                            {"property": "Etiqueta", "select":     {"equals": label}},
                        ]
                    }
                },
            )
            resp.raise_for_status()
            pages = resp.json().get("results", [])

        tasks = []
        for page in pages:
            props = page.get("properties", {})
            title = _extract_title(props)
            status = _extract_status(props)
            tasks.append(NotionTask(
                id=page["id"],
                title=title,
                label=label,
                status=status,
                url=page.get("url", ""),
            ))
        return tasks

    async def update_task_progress(self, task_id: str, progress: int, log: str) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.patch(
                f"{_BASE}/pages/{task_id}",
                headers=_headers(),
                json={
                    "properties": {
                        "Status": {"select": {"name": "En progreso"}},
                        "Progress": {"number": progress},
                    }
                },
            )
            # Append log as a comment block
            await client.patch(
                f"{_BASE}/pages/{task_id}",
                headers=_headers(),
                json={
                    "properties": {
                        "Log": {"rich_text": [{"text": {"content": log[:2000]}}]}
                    }
                },
            )

    async def complete_task(self, task_id: str, result: str, cost_usd: float) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.patch(
                f"{_BASE}/pages/{task_id}",
                headers=_headers(),
                json={
                    "properties": {
                        "Status": {"select": {"name": "Completado"}},
                        "Result": {"rich_text": [{"text": {"content": result[:2000]}}]},
                        "Cost USD": {"number": round(cost_usd, 6)},
                    }
                },
            )

    async def attach_screenshot(self, task_id: str, image_bytes: bytes) -> None:
        # Solo si el usuario pidió capturas explícitamente (opt-in) — Fase 8
        raise NotImplementedError("attach_screenshot es opt-in y se implementa en Fase 8")

    async def search_pages(self, query: str, page_size: int = 20) -> list[dict]:
        """Busca páginas y bases de datos accesibles por texto libre."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{_BASE}/search",
                headers=_headers(),
                json={"query": query, "page_size": page_size},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

        items = []
        for r in results:
            obj_type = r.get("object")
            if obj_type == "page":
                props = r.get("properties", {})
                title = _extract_title(props)
                items.append({"type": "page", "id": r["id"], "title": title, "url": r.get("url", "")})
            elif obj_type == "database":
                title_parts = r.get("title", [])
                title = "".join(p.get("plain_text", "") for p in title_parts)
                items.append({"type": "database", "id": r["id"], "title": title, "url": r.get("url", "")})
        return items

    async def list_database_items(self, board: str, page_size: int = 50) -> list[dict]:
        """Lista todos los items de una base de datos sin filtro de etiqueta."""
        if board not in settings.notion_watched_boards:
            raise PermissionError(f"Tablero '{board}' no está en NOTION_WATCHED_BOARDS")

        db_id = await self._search_database(board)
        if not db_id:
            raise ValueError(f"Tablero '{board}' no encontrado en Notion. ¿Compartiste el tablero con la integración?")

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{_BASE}/databases/{db_id}/query",
                headers=_headers(),
                json={"page_size": page_size},
            )
            resp.raise_for_status()
            pages = resp.json().get("results", [])

        items = []
        for page in pages:
            props = page.get("properties", {})
            items.append({
                "id": page["id"],
                "title": _extract_title(props),
                "status": _extract_status(props),
                "url": page.get("url", ""),
            })
        return items

    async def get_page_content(self, page_id: str) -> dict:
        """Lee el contenido de una página específica (bloques de texto)."""
        async with httpx.AsyncClient(timeout=15) as client:
            # Metadata de la página
            page_resp = await client.get(
                f"{_BASE}/pages/{page_id}",
                headers=_headers(),
            )
            page_resp.raise_for_status()
            page = page_resp.json()

            # Bloques de contenido
            blocks_resp = await client.get(
                f"{_BASE}/blocks/{page_id}/children",
                headers=_headers(),
                params={"page_size": 100},
            )
            blocks_resp.raise_for_status()
            blocks = blocks_resp.json().get("results", [])

        title = _extract_title(page.get("properties", {}))
        text_blocks = []
        for b in blocks:
            b_type = b.get("type", "")
            block_data = b.get(b_type, {})
            rich_text = block_data.get("rich_text", [])
            text = "".join(rt.get("plain_text", "") for rt in rich_text)
            if text:
                text_blocks.append(text)

        return {"id": page_id, "title": title, "url": page.get("url", ""), "content": "\n".join(text_blocks)}


def _extract_title(props: dict) -> str:
    for key in ("Name", "Nombre", "Title", "Título"):
        if key in props:
            parts = props[key].get("title", [])
            return "".join(p.get("plain_text", "") for p in parts)
    return "(sin título)"


def _extract_status(props: dict) -> str:
    for key in ("Status", "Estado"):
        if key in props:
            prop = props[key]
            if "select" in prop and prop["select"]:
                return prop["select"].get("name", "")
            if "status" in prop and prop["status"]:
                return prop["status"].get("name", "")
    return "unknown"
