# CLAUDE.md — Guía completa del proyecto Agente Orquestador

> **Para Claude Code**: leer este archivo COMPLETO antes de escribir cualquier línea de código.
> **Para el equipo de hosting (Windows)**: ir directo a la sección "Setup Windows".
> Referencia de seguridad: SECURITY.md en esta misma carpeta.

---

## REGLA DE ORO (Claude Code)

**Todo cambio de infraestructura, nueva feature, nuevo endpoint, nuevo tool, nuevo modelo de DB o cambio
arquitectónico DEBE quedar reflejado en este archivo en la misma sesión en que se implementa.**

Al iniciar una sesión de Claude Code sobre este repo:
1. Leer CLAUDE.md completo — es la fuente de verdad del estado actual
2. Verificar qué fases tienen `[x]`
3. Leer PROGRESS.md si existe (estado de trabajo en curso)
4. NO reescribir lo que ya funciona

---

## Estado actual del proyecto

```
FASE 0: [x] Infra Docker local
FASE 1: [x] Backend core + orquestador + Telegram
FASE 2: [x] Router inteligente
FASE 3: [x] Web UI
FASE 4: [x] Notion como fuente de tareas
FASE 5: [x] Sub-agentes especializados
FASE 6: [x] Gmail + Calendar + Watchers
FASE 7: [x] Claude Code bridge
FASE 7.5: [x] Voz — hotkey Mac + audio Telegram
FASE 8: [x] Agente Chrome
FASE 9: [x] Tareas programadas + Gmail/Calendar activos + memoria de sesión
FASE 10: [x] Playbooks + sub_webdev + live console streaming
FASE 11: [x] GitHub integration + Worker SSE badge
```

---

## SETUP WINDOWS — Hosting del servicio

Esta sección es para el equipo que va a hostear el sistema en Windows.
El backend corre 100% en Docker, así que la mayoría del setup es igual que en Linux/macOS.

### Requisitos previos

| Herramienta | Versión mínima | Instalación |
|---|---|---|
| Docker Desktop | 4.x | https://www.docker.com/products/docker-desktop — usar backend WSL2 |
| Git | cualquiera | https://git-scm.com/download/win |
| Node.js | 20+ | https://nodejs.org (solo si quieren correr el frontend local) |

**Configuración recomendada de Docker Desktop en Windows:**
- Settings → General → "Use WSL 2 based engine" ✅
- Settings → Resources → WSL Integration → habilitar tu distro Linux ✅
- Memory: mínimo 4 GB asignados al Docker engine

### 1. Clonar el repositorio

```powershell
git clone https://github.com/lucascatro29/Agente_Orquestador.git
cd Agente_Orquestador
```

### 2. Configurar variables de entorno

```powershell
copy .env.example .env
notepad .env
```

Ver sección **Variables de entorno** más abajo para documentación completa de cada variable.

### 3. Levantar todos los servicios

```powershell
docker compose up --build -d
```

Esto levanta: `postgres`, `redis`, `backend`, `worker`, `celery-beat`.

### 4. Verificar que todo esté corriendo

```powershell
docker compose ps
# Todos deben mostrar "Up" o "healthy"

curl http://localhost:8000/health
# Debe retornar: {"status":"ok"}
```

### 5. Frontend (opcional — si quieren la UI web)

```powershell
cd frontend
npm install
npm run dev
# Abre http://localhost:3000 en el browser
```

O en producción:
```powershell
npm run build
npm start
```

### 6. Apagar los servicios

```powershell
docker compose down
# Los datos en volúmenes (postgres_data) se conservan
```

### Comandos de mantenimiento

```powershell
# Ver logs del backend en tiempo real
docker compose logs -f backend

# Ver logs del worker (Celery)
docker compose logs -f worker

# Ver logs del beat scheduler
docker compose logs -f celery-beat

# Reiniciar solo el backend (después de cambios en .env)
docker compose restart backend

# Reiniciar todo
docker compose down && docker compose up -d

# Ver uso de recursos
docker stats

# Ejecutar comando dentro del container
docker compose exec backend python -c "from app.config import settings; print(settings.anthropic_api_key[:10])"

# Correr migraciones de DB manualmente (si es necesario)
docker compose exec backend alembic upgrade head
```

### Paths importantes en Windows

- `.env` → mismo directorio que `docker-compose.yml` (raíz del repo)
- `ALLOWED_WORKING_DIRS` → rutas **dentro del container Docker** (siempre con `/`), no rutas de Windows
- Los volúmenes de Docker (`postgres_data`, `piper_voices`) se guardan en el área de Docker, no en el filesystem de Windows

### Diferencias Windows vs macOS

| Aspecto | Windows (hosting) | macOS (desarrollo) |
|---|---|---|
| Script inicio | `docker compose up -d` | `./start.sh` |
| Frontend | `npm run dev` en PowerShell | incluido en `start.sh` |
| Hotkey de voz | No disponible sin setup local | `Cmd+<` via `scripts/hotkey_voice.py` |
| Paths en .env | Usar rutas del container (`/app/...`) | Usar rutas del container |
| TTS | Funciona en Docker (Piper+ffmpeg+espeak-ng) | igual |
| Chrome agent | Funciona en Docker (Chromium headless) | igual |

---

## Variables de entorno (.env)

Copiar de `.env.example` y completar. Las marcadas con `(requerida)` bloquean el inicio si faltan.

### Core

```bash
# Requerida — API key de Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Requerida — token de autenticación para los endpoints /api/*
APP_AUTH_TOKEN=string-random-seguro-cambiar

# Auto-configuradas por docker-compose — no cambiar salvo hosting externo
DATABASE_URL=postgresql+asyncpg://agents:agents_local_dev@postgres:5432/agents
REDIS_URL=redis://redis:6379/0
```

### Telegram

```bash
# Requerido para recibir/enviar mensajes por Telegram
TELEGRAM_BOT_TOKEN=123456789:ABC...   # obtener de @BotFather en Telegram
TELEGRAM_ALLOWED_CHAT_ID=123456789    # tu chat_id personal (solo este puede usar el bot)
TELEGRAM_WEBHOOK_SECRET=              # opcional, solo si usás webhook en lugar de polling
```

Para obtener tu chat_id: escribirle al bot @userinfobot en Telegram.

### Notion

```bash
# Requerido para tools de Notion
NOTION_API_TOKEN=secret_...           # Integration token de https://www.notion.so/my-integrations
NOTION_WATCHED_BOARDS=["Sprint Backend","Proyectos 2026"]  # lista JSON de tableros accesibles
```

El token de integración debe tener acceso a los tableros listados en `NOTION_WATCHED_BOARDS`.

### Google (Gmail + Calendar)

El sistema usa OAuth2 con refresh token (no vence). Setup de una sola vez:

```bash
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-...
GOOGLE_REFRESH_TOKEN=1//...

# Legado (access tokens directos — vencen en 1h — no usar en producción)
GMAIL_OAUTH_TOKEN=
CALENDAR_OAUTH_TOKEN=
```

**Cómo obtener las credenciales Google (una sola vez):**
1. Ir a https://console.cloud.google.com → APIs & Services → Credentials
2. Crear OAuth 2.0 Client ID → Application type: "Desktop app"
3. Habilitar en la consola: Gmail API, Google Calendar API, Google Drive API
4. Descargar el `credentials.json` generado
5. Copiar `credentials.json` a `scripts/credentials.json`
6. Correr el script de autorización:
   ```bash
   # macOS/Linux
   python scripts/get_google_tokens.py
   # Windows — en PowerShell
   python scripts\get_google_tokens.py
   ```
7. Completar el flujo OAuth en el browser que se abre
8. El script imprime `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`
9. Pegar esos valores en `.env`

**Scopes usados**: `gmail.modify`, `calendar`, `drive` (read-write)

```bash
# Watchers automáticos (Celery beat)
GMAIL_WATCHER_ENABLED=false        # true = revisa inbox cada 15 min
GMAIL_WATCHED_LABELS=["INBOX"]
CALENDAR_WATCHER_ENABLED=false     # true = revisa calendario cada 30 min
```

### Seguridad y costos

```bash
# Directorios donde el orquestador puede lanzar Claude Code
# Rutas DENTRO del container Docker (Unix)
ALLOWED_WORKING_DIRS=["/app/proyectos","/home/dev/repos"]

# Límites de costo automáticos
MAX_COST_PER_SESSION_USD=5.0       # pausa la sesión si supera este costo
MAX_COST_PER_DAY_USD=20.0          # pausa el día si supera este costo

# Modo estricto de seguridad
SECURITY_STRICT_MODE=true
SECURITY_NOTIFY_LEVEL=warning      # "info" | "warning" | "critical"
```

### Chrome agent

```bash
# Dominios que el agente Chrome puede navegar (lista blanca)
CHROME_ALLOWED_DOMAINS=["instagram.com","linkedin.com"]
```

### Voz y transcripción

```bash
# Para transcripción de audio de Telegram (Whisper)
OPENAI_API_KEY=sk-...              # opcional, si no se usa faster-whisper local
WHISPER_MODEL=base                 # tiny | base | small | medium (solo modo local)
```

---

## Arquitectura del sistema

### Servicios Docker

```
┌─────────────────────────────────────────────────────────────┐
│                    docker-compose                           │
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐  │
│  │ postgres │   │  redis   │   │ backend  │   │ worker │  │
│  │  :5432   │   │  :6379   │   │  :8000   │   │        │  │
│  └──────────┘   └──────────┘   └──────────┘   └────────┘  │
│       ↑               ↑ broker      ↑                ↑     │
│       └───────────────┼─────────────┘                │     │
│                       │                     ┌──────────────┐│
│                       └─────────────────────│ celery-beat  ││
│                                             └──────────────┘│
└─────────────────────────────────────────────────────────────┘
                         ↑
               frontend (Next.js :3000) — externo al compose
```

### Flujo de un mensaje

```
Usuario (Web UI / Telegram)
    → POST /api/chat/stream  (SSE) o POST /api/chat
    → AgentRunner.run_routed()
        → MessageRouter.classify()  [Haiku — classifica en ~$0.0001]
            ↓
        → Si consulta_simple → _run_direct_haiku()
        → Si complejo → _build_filtered_agent() → runner.run()
            → Loop agéntico con tools
            → Si tool.requires_confirmation=True → PendingApproval → pausa
            → Si create_subagent / run_claude_code → WorkerManager → Celery task
    → Persistir en DB (messages, tool_traces)
    → Calcular costo → footer → respuesta
```

### Celery beat schedule (tareas automáticas)

```
*/1 min  → workers.run_due_scheduled_tasks   (ejecuta tareas programadas vencidas)
*/15 min → watchers.check_mail               (si GMAIL_WATCHER_ENABLED=true)
*/30 min → watchers.check_calendar           (si CALENDAR_WATCHER_ENABLED=true)
```

---

## ESTADO REAL DEL CÓDIGO

Estado actual del código — diferencias vs spec original y detalles de implementación.

### Telegram: usa POLLING, no webhook

- `app/telegram/polling.py` — loop de polling en background (no requiere URL pública ni ngrok)
- Se inicia en `main.py` como `asyncio.create_task(run_polling())`
- El webhook sigue en `app/telegram/webhook.py` pero no se usa actualmente

### Router: categorías disponibles

```
consulta_simple | notion_tasks | coding | web_dev | admin_email | admin_calendar |
analisis | arquitectura | tareas_programadas | navegacion_chrome
```

`web_dev`: landing pages, sitios Next.js/React, frontend, animaciones → routea con tools para sub_webdev

### GitHub integration (Fase 11)

- `GITHUB_TOKEN` y `GITHUB_USERNAME` en `.env` y `config.py`
- Dockerfile: instala `git`, configura `user.email`, `user.name`, `credential.helper store`
- `tasks.py`: al lanzar Claude Code, escribe `/tmp/.git-credentials` con el token → `git push` funciona sin config extra
- Tool `github_create_pr`: abre PR via GitHub API (httpx). Acepta `repo` sin owner (usa `GITHUB_USERNAME`) o con owner (`owner/repo`)
- Sub-agentes `sub_webdev` y `sub_dev`: tienen `github_create_pr` en `allowed_tools` y sus prompts incluyen instrucciones de push + PR
- Flujo estándar: trabajar en rama feature → `git push` → `github_create_pr`

### Worker SSE badge (Fase 11)

- Endpoint: `GET /api/workers/stream?token=...` — SSE que sondea DB cada 2s, emite solo cuando cambia el estado
- Token via query param (EventSource del browser no soporta headers custom)
- `WorkerBadge.tsx` — componente en el header que se conecta al SSE y muestra "● N workers activos" con animación de ping
- Se oculta cuando `active_count === 0`, aparece automáticamente cuando hay workers corriendo
- Al hacer click abre el ConsolasPanel
- **Cero tokens LLM** — solo HTTP + DB

### Tools disponibles en el registry

```python
# Memoria
get_memoria, update_memoria, delete_memoria, search_memoria, remember_session

# Workers y Claude Code
run_claude_code, get_workers_status, cancel_worker

# Sub-agentes
create_subagent

# Notion
notion_get_tasks, notion_search, notion_list_database, notion_get_page,
notion_create_task, notion_update_task

# Gmail + Calendar (activos, on-demand)
read_gmail_inbox, read_calendar_events

# Tareas programadas
schedule_task, list_scheduled_tasks, delete_scheduled_task, toggle_scheduled_task

# Chrome agent
chrome_navigate, chrome_screenshot

# Playbooks (Fase 10)
save_playbook, list_playbooks, get_playbook, run_playbook, update_playbook, delete_playbook

# GitHub (Fase 11)
github_create_pr
```

### Categorías de memoria

```
objetivo_actual | proyecto | preferencia | persona | recordatorio | nota_libre | sesion_pasada
```

`sesion_pasada` se usa con `remember_session` para guardar resúmenes cross-sesión.

### Sub-agentes especializados (Fase 5)

El orquestador puede instanciar sub-agentes con la tool `create_subagent`.

**Flujo de llamada (verificado en código):**
```
Orquestador → create_subagent tool (requires_confirmation=False)
    → _handle_create_subagent(worker_mgr, session_id, type, name, objective, ...)
        → WorkerManager.create() → row en tabla workers
        → execute_subagent.delay(worker_id, type, objective, working_dir, session_id)
            → Celery task: get_subagent(type) → AgentConfig → AgentRunner.run()
            → Resultado guardado como mensaje del asistente + notificación Telegram
```

**Sub-agentes disponibles:**

```python
"sub_webdev": {
    # Senior Frontend Engineer + Motion Designer
    # Especialidad: Next.js 15 + Tailwind CSS + TypeScript + animaciones Apple-style
    # scroll-driven video, landing pages cinematográficas, GSAP + ScrollTrigger
    # Trabaja directamente sobre repos Git: inspecciona, crea rama, implementa, valida build, abre PR
    model: "claude-sonnet-4-6",
    allowed_tools: [
        "run_claude_code", "get_workers_status", "cancel_worker",
        "get_memoria", "update_memoria", "search_memoria",
    ],
    forbidden_tools: ["create_subagent"],
    max_workers: 5,
    max_duration_minutes: 240,   # 4 horas — tareas de web dev son largas
    approval_policy: "confirm_writes",
    # Al crear: siempre incluir en el objective el repo path + estética/referencia + feature a implementar
    # Guarda progreso en memoria con key webdev_progreso_[nombre_proyecto]
}

"sub_dev": {
    # Dev senior backend/fullstack general
    model: "claude-sonnet-4-6",
    allowed_tools: [
        "run_claude_code", "get_workers_status", "cancel_worker",
        "get_memoria", "update_memoria",
        "notion_get_tasks", "notion_search", "notion_list_database", "notion_get_page",
    ],
    forbidden_tools: ["create_subagent"],  # evita recursión
    max_workers: 5,
    max_duration_minutes: 120,
    approval_policy: "confirm_writes",
}

"sub_analista": {
    model: "claude-sonnet-4-6",
    allowed_tools: [
        "run_claude_code", "get_workers_status",
        "get_memoria", "update_memoria",
        "notion_search", "notion_list_database", "notion_get_page",
        "read_gmail_inbox",
    ],
    forbidden_tools: ["create_subagent", "cancel_worker"],
    max_workers: 3,
    max_duration_minutes: 60,
    approval_policy: "auto",
}
```

**Nota sobre confirmación**: `create_subagent` tiene `requires_confirmation=False` — el orquestador puede crear sub-agentes sin pedir confirmación al usuario. Si querés cambiar esto, modificar `requires_confirmation=True` en `registry.py:784`.

**Cuándo usar sub-agentes** (documentado en system prompt del orquestador):
- La tarea requiere múltiples sesiones de Claude Code coordinadas
- Trabajo estimado > 30 min
- Querés delegar un objetivo completo y recibir el resultado final

### Claude Code bridge (Fase 7)

- Hook `Stop` en `~/.claude/settings.json` → `scripts/notify_stop.py` → `POST /api/workers/hook`
- El orquestador evalúa y decide si notificar por Telegram
- `run_claude_code` tool: lanza `claude --print <prompt>` en Celery worker
- Si `claude` CLI no está instalado en el container → falla con mensaje claro

**Para que `run_claude_code` funcione**, Claude Code CLI debe estar instalado en el container `worker`:
```dockerfile
# Agregar en backend/Dockerfile si se quiere habilitar
RUN npm install -g @anthropic-ai/claude-code
```

### TTS — Text-to-Speech

- Motor: **Piper TTS** v1.4.x — voz `es_ES-davefx-medium`
- API actual de Piper v1.4: `voice.synthesize(text)` → `Iterable[AudioChunk]` (no `wave_file` directo)
- Dependencias del sistema en Dockerfile: `ffmpeg`, `espeak-ng`
- Pre-carga al arrancar en `main.py`
- Endpoint: `POST /api/tts/synthesize` → `audio/wav`
- Web UI: toggle ON/OFF en barra superior (localStorage `tts_enabled`)
  - Usa `AudioContext` (Web Audio API) — necesario para evitar bloqueo de autoplay del browser
- Telegram: envía audio OGG Opus via `sendVoice` después de cada respuesta

### Chrome agent (Fase 8)

- Motor: **Playwright** v1.44.0 — Chromium headless (Linux, dentro del container)
- Lista blanca: `CHROME_ALLOWED_DOMAINS` en `.env`
- Detecta texto oculto: `display:none`, `visibility:hidden`, `opacity:0`, `font-size<2px`
- Si detecta injection: bloquea, captura screenshot, devuelve `flagged=True`
- Acciones bloqueadas hardcoded: instalar extensiones, descargas, permisos del browser, JS inyectado

### Voz local (Fase 7.5) — solo macOS/Windows de desarrollo

- Web: Web Speech API en `InputBar.tsx` (micrófono nativo del browser)
- Telegram: audio → faster-whisper → texto al agente
- Hotkey global:
  - macOS: `scripts/hotkey_voice.py` — `Cmd+<`
  - Windows: `scripts/hotkey_voice.py` — `Ctrl+<`
- No requerido para el hosting del servicio

### DB: tablas existentes

```
sessions, messages, memory, pending_approvals, tool_traces, security_events,
workers, watcher_state, scheduled_tasks, playbooks
```

### Web UI: componentes principales

```
components/chat/ChatWindow.tsx      — chat + SSE streaming
components/chat/MessageBubble.tsx   — render mensajes + footer costo
components/chat/InputBar.tsx        — input con botón de voz (Web Speech API)
components/layout/Sidebar.tsx       — sesiones con título auto + botón eliminar
components/layout/RightPanel.tsx    — tabs: Agentes | Memoria | Flujos | Workers | Seg.
components/panels/MemoryPanel.tsx
components/panels/SecurityPanel.tsx
components/panels/AgentsPanel.tsx
components/panels/PlaybooksPanel.tsx  — tab "Flujos": lista, run, delete playbooks
components/panels/ConsolasPanel.tsx   — panel inferior colapsable: live output de workers
```

### API endpoints (todos prefijados con /api)

```
POST   /api/chat
POST   /api/chat/stream              (SSE)
GET    /api/sessions
DELETE /api/sessions/{id}
GET    /api/sessions/{id}/messages
GET    /api/memory
POST   /api/memory
DELETE /api/memory/{id}
GET    /api/approvals
POST   /api/approvals/{id}
GET    /api/security/events
POST   /api/security/events/{id}/resolve
POST   /api/security/events/{id}/retry
GET    /api/workers
GET    /api/workers/stream              (SSE — token via query param, cero LLM)
POST   /api/workers/hook
GET    /api/schedule
GET    /api/scheduled-tasks
DELETE /api/scheduled-tasks/{id}
PATCH  /api/scheduled-tasks/{id}/toggle
GET    /api/agents
POST   /api/transcribe
POST   /api/tts/synthesize
GET    /api/playbooks
POST   /api/playbooks
GET    /api/playbooks/{id}
PATCH  /api/playbooks/{id}
DELETE /api/playbooks/{id}
POST   /api/playbooks/{id}/run
GET    /health
```

### Modelos de precios (tracker.py)

```python
PRICES = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
    "claude-haiku-4-5":  {"input": 1.0, "output":  5.0, "cache_read": 0.1},
    "claude-opus-4-7":   {"input": 5.0, "output": 25.0, "cache_read": 0.5},
}
# Nunca hardcodear precios — siempre desde este dict
```

---

## Setup macOS (desarrollo)

### Requisitos

```bash
# Una sola vez
pip install -r scripts/requirements_local.txt
# incluye: pynput sounddevice scipy numpy httpx plyer
```

### Iniciar todo

```bash
./start.sh
# Hace: Docker → health check → frontend (localhost:3000) → hotkey de voz (Cmd+<)
```

### Apagar

```bash
docker compose down
```

---

## Convenciones del proyecto (no negociables)

```python
# Type hints obligatorios en funciones públicas
async def chat(req: ChatRequest, db: AsyncSession) -> ChatResponse: ...

# Async por default — FastAPI + SQLAlchemy async
async with AsyncSessionLocal() as session: ...

# Pydantic v2 — no v1
from pydantic import BaseModel
class Config(BaseModel):
    model_config = SettingsConfigDict(...)

# Imports ordenados: stdlib → third-party → app
import json
from datetime import datetime
import anthropic
from fastapi import FastAPI
from app.db import get_db

# Docstrings en castellano para lógica de negocio
async def clasificar_mensaje(texto: str) -> RouteResult:
    """Clasifica el mensaje entrante y determina qué agente y contexto usar."""
```

---

## Repositorio GitHub

```
Usuario:     lucascatro29
Email:       lucascastro2929@gmail.com
Repo:        Agente_Orquestador
URL:         https://github.com/lucascatro29/Agente_Orquestador
Directorio:  /Users/lucascastro/Desktop/Lucas/lucascastro2929 Github/Agente_Orquestador
```

### Convenciones de commits

```
feat:     nueva funcionalidad
fix:      corrección de bug
chore:    cambios de infra/config sin lógica de negocio
docs:     cambios solo en documentación
test:     tests sin cambios de código
refactor: refactor sin nueva funcionalidad ni fix
```

### Protocolo de push

```bash
git add .
git commit -m "tipo: descripción en minúscula"
git push origin main
```

---

## Protocolo de corte de contexto (Claude Code)

Si estás por quedarte sin tokens:

1. Escribís `PROGRESS.md` con:
   - Último archivo modificado
   - Próximo paso exacto
   - Decisiones tomadas que no estén en CLAUDE.md
2. Hacés commit: `WIP: [descripción de dónde quedó]`

Al retomar, leer PROGRESS.md antes que nada.

---

## Qué NO hacer nunca

- No instalar dependencias no listadas en `requirements.txt` sin agregarlas.
- No cambiar los modelos de DB de fases anteriores (solo agregar columnas/tablas).
- No hardcodear precios, tokens, o credenciales.
- No implementar bypass de seguridad.
- No acceder a tableros de Notion fuera de `NOTION_WATCHED_BOARDS`.
- No ejecutar Claude Code fuera de `ALLOWED_WORKING_DIRS`.
- No saltear las validaciones de `SecurityValidator` antes de ejecutar tools.

---

## Historial de implementación (referencia)

Las fases 0-10 están completas. Ver commits del repo para el detalle de cada implementación.
El código real en `backend/app/` es la fuente de verdad — este archivo documenta el estado actual,
no la spec original (que puede diferir en detalles de implementación).

### Cambios relevantes respecto a la spec original

| Componente | Spec original | Implementación real |
|---|---|---|
| Telegram | webhook | polling (no requiere URL pública) |
| `create_subagent` | `requires_confirmation=True` | `requires_confirmation=False` |
| Piper TTS API | `synthesize(text, wave_file)` | `synthesize(text)` → `Iterable[AudioChunk]` |
| Google OAuth | access token legacy | refresh token (no vence) |
| Haiku model ID | `claude-haiku-4-5` | `claude-haiku-4-5-20251001` |
| Router `opus` | sugería opus cuando aplica | bloqueado — nunca se usa sin auth explícita del usuario |
| `run_claude_code` worker | subprocess síncrono | asyncio subprocess con streaming live a DB (15 líneas/flush) |
| system prompt cache | bloque único con memoria | sistema separado: bloque estático cacheado + memoria dinámica sin cache |
| ConsolasPanel | tab en RightPanel | panel colapsable en bottom de la pantalla, auto-abre al lanzar worker |
