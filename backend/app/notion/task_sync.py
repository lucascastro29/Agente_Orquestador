"""Integración con Notion para leer y actualizar tareas etiquetadas."""
import re
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


def _normalize(name: str) -> str:
    """Normaliza nombre de tablero: lower, elimina espacios alrededor de / y colapsa espacios."""
    n = re.sub(r'\s*([/\\])\s*', r'\1', name)
    return " ".join(n.lower().split())


class NotionTaskSync:

    def _is_allowed_board(self, board: str) -> bool:
        norm = _normalize(board)
        return any(_normalize(b) == norm for b in settings.notion_watched_boards)

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
                if _normalize(title) == _normalize(board_name):
                    return r["id"]
        return None

    async def get_tasks_by_label(self, board: str, label: str) -> list[NotionTask]:
        """Lee tareas de un tablero filtradas por etiqueta."""
        if not self._is_allowed_board(board):
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

    async def _get_page_properties(self, page_id: str) -> dict:
        """Devuelve el schema de propiedades de una página (nombre → tipo)."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/pages/{page_id}", headers=_headers())
            resp.raise_for_status()
            return {k: v.get("type") for k, v in resp.json().get("properties", {}).items()}

    async def _get_database_schema(self, db_id: str) -> dict:
        """Devuelve el schema completo de una base de datos (nombre → {type, ...})."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_BASE}/databases/{db_id}", headers=_headers())
            resp.raise_for_status()
            return resp.json().get("properties", {})

    async def create_task(
        self,
        board: str,
        title: str,
        status: str | None = None,
        description: str | None = None,
    ) -> dict:
        """Crea una nueva tarea en un tablero de Notion."""
        if not self._is_allowed_board(board):
            raise PermissionError(f"Tablero '{board}' no está en NOTION_WATCHED_BOARDS")

        db_id = await self._search_database(board)
        if not db_id:
            raise ValueError(f"Tablero '{board}' no encontrado en Notion")

        schema = await self._get_database_schema(db_id)
        properties: dict = {}

        # Propiedad título — buscar la de tipo "title" en el schema real
        for prop_name, prop_info in schema.items():
            if prop_info.get("type") == "title":
                properties[prop_name] = {"title": [{"text": {"content": title}}]}
                break
        if not properties:
            properties["Name"] = {"title": [{"text": {"content": title}}]}

        # Estado
        if status:
            for prop_name in ("Status", "Estado", "Etapa"):
                if prop_name in schema:
                    ptype = schema[prop_name].get("type")
                    if ptype == "status":
                        properties[prop_name] = {"status": {"name": status}}
                    elif ptype == "select":
                        properties[prop_name] = {"select": {"name": status}}
                    break

        # Descripción
        if description:
            for prop_name in ("Description", "Descripción", "Notas", "Notes", "Detalle"):
                if prop_name in schema and schema[prop_name].get("type") == "rich_text":
                    properties[prop_name] = {
                        "rich_text": [{"text": {"content": description[:2000]}}]
                    }
                    break

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{_BASE}/pages",
                headers=_headers(),
                json={"parent": {"database_id": db_id}, "properties": properties},
            )
            resp.raise_for_status()
            page = resp.json()

        return {"id": page["id"], "title": title, "url": page.get("url", ""), "board": board}

    async def update_task_progress(self, task_id: str, progress: int, log: str) -> None:
        props = await self._get_page_properties(task_id)
        update: dict = {}

        # Status: buscar columna de tipo status o select
        for name in ("Status", "Estado", "Etapa"):
            if name in props:
                ptype = props[name]
                if ptype == "status":
                    update[name] = {"status": {"name": "En progreso"}}
                elif ptype == "select":
                    update[name] = {"select": {"name": "En progreso"}}
                break

        # Progress: columna numérica
        for name in ("Progress", "Progreso", "Avance"):
            if name in props and props[name] == "number":
                update[name] = {"number": progress}
                break

        # Log: columna de texto enriquecido
        for name in ("Log", "Notas", "Notes", "Descripción"):
            if name in props and props[name] == "rich_text":
                update[name] = {"rich_text": [{"text": {"content": log[:2000]}}]}
                break

        if not update:
            return  # No hay columnas conocidas — ignorar silenciosamente

        async with httpx.AsyncClient(timeout=15) as client:
            await client.patch(
                f"{_BASE}/pages/{task_id}",
                headers=_headers(),
                json={"properties": update},
            )

    async def complete_task(self, task_id: str, result: str, cost_usd: float) -> None:
        props = await self._get_page_properties(task_id)
        update: dict = {}

        for name in ("Status", "Estado", "Etapa"):
            if name in props:
                ptype = props[name]
                if ptype == "status":
                    update[name] = {"status": {"name": "Completado"}}
                elif ptype == "select":
                    update[name] = {"select": {"name": "Completado"}}
                break

        for name in ("Result", "Resultado", "Notas", "Notes"):
            if name in props and props[name] == "rich_text":
                update[name] = {"rich_text": [{"text": {"content": result[:2000]}}]}
                break

        for name in ("Cost USD", "Costo", "Cost"):
            if name in props and props[name] == "number":
                update[name] = {"number": round(cost_usd, 6)}
                break

        if not update:
            return

        async with httpx.AsyncClient(timeout=15) as client:
            await client.patch(
                f"{_BASE}/pages/{task_id}",
                headers=_headers(),
                json={"properties": update},
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
        if not self._is_allowed_board(board):
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
    # Primero buscar por nombres conocidos
    for key in ("Name", "Nombre", "Title", "Título", "Tarea", "Task"):
        if key in props and props[key].get("type") == "title":
            parts = props[key].get("title", [])
            return "".join(p.get("plain_text", "") for p in parts)
    # Fallback: buscar cualquier propiedad de tipo title
    for prop in props.values():
        if prop.get("type") == "title":
            parts = prop.get("title", [])
            text = "".join(p.get("plain_text", "") for p in parts)
            if text:
                return text
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
