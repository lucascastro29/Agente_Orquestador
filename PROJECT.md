# Claude Agents — Documentación del Proyecto

> Documento de contexto para sesiones de Claude Code y Projects de Claude.ai.
> Pegá este archivo entero como contexto inicial cuando arranques una sesión nueva.
> Actualizá este documento cuando avances de fase o tomes decisiones nuevas.

---

## 1. Visión del sistema

Un **sistema jerárquico de agentes** donde yo le hablo al orquestador por Telegram o Web UI, y él coordina todo lo demás:

```
YO
 │
 ▼
ORQUESTADOR  ←→  Telegram + Web UI
 │
 ├──► Sub-agente especializado A  →  Sus Claude Code sessions
 ├──► Sub-agente especializado B  →  Sus Claude Code sessions
 │
 ├──► Claude Code Session directa (tareas simples)
 │
 └──► Notion (tableros etiquetados como fuente de tareas)
        ├─ Tareas con etiqueta "CLAUDE CODE"  →  workers de Claude Code
        └─ Tareas con etiqueta "CLAUDE ANALISTA" →  sub-agente analista
```

**El orquestador es el único punto de contacto conmigo.** Yo nunca hablo directo con sessions ni sub-agentes. Él delega, monitorea, consolida y reporta.

**Al final de cada mensaje** el orquestador incluye automáticamente el consumo de la interacción en tokens y en dólares.

Es un sistema **mono-usuario**. No es un producto para terceros.

---

## 2. Quién soy / contexto del usuario

- Desarrollador, manejo APIs y código sin problema.
- Stack cómodo: Python y TypeScript.
- Prefiero soluciones simples sobre frameworks pesados.
- Uso **Notion a diario**: proyectos, notas, tareas, tableros de trabajo.
- Uso **Claude Code** regularmente — en este sistema es el ejecutor técnico.
- **Cowork descartado**: no tiene API ni webhooks, no es controlable programáticamente.
- Los tableros de Notion son fuente de tareas para los agentes (ver sección 7).
- Las tareas son ad-hoc, no recurrentes.

---

## 3. Decisiones de modelos

### Política de modelos por nivel y tipo de tarea

| Rol | Modelo | Razón |
|---|---|---|
| **Orquestador** | **Sonnet 4.6** | Coordinación, delegación, tool use multi-paso, memory. No bajar de Sonnet: Haiku falla en tool selection y planning agéntico. |
| **Sub-agentes especializados** | **Sonnet 4.6** | Mismo razonamiento: loop propio + tool use + múltiples workers. |
| **Watchers** (mail, calendar) | **Haiku 4.5** | Clasificación simple: ¿es relevante o no? Alto volumen, bajo costo. |
| **Worker de resumen** | **Haiku 4.5** | Generar `result_summary` de output de Claude Code. Tarea estructurada. |
| **Triage de Notion** | **Haiku 4.5** | Clasificar qué etiqueta tiene una tarea y a qué agente va. |
| **Escalado puntual** | **Opus 4.7** | Solo cuando Sonnet claramente no alcanza (razonamiento muy complejo, diseño de arquitectura crítica). No es el default de nada. |

**Regla**: el ahorro real no viene de bajar el modelo del orquestador — viene de usar Haiku en las tareas periféricas de alto volumen, y de que el trabajo pesado corre en Claude Code (suscripción, no API).

### Precios de referencia (mayo 2026, por millón de tokens)

| Modelo | Input | Output | Cache read |
|---|---|---|---|
| Opus 4.7 | $5 | $25 | $0.50 |
| Sonnet 4.6 | $3 | $15 | $0.30 |
| Haiku 4.5 | $1 | $5 | $0.10 |

Prompt caching activado en todos los agentes propios.

---

## 4. Consumo de tokens y costos — en cada mensaje

### Qué se muestra al final de cada respuesta del orquestador

Tanto en Telegram como en Web UI, al final de **cada mensaje** el orquestador incluye un bloque de consumo:

```
─────────────────────────────
💬 Este mensaje
   Input:      1.240 tok  →  $0.0037
   Output:       380 tok  →  $0.0057
   Cache hit:  3.800 tok  →  $0.0011  (ahorro: $0.0102)
   Subtotal:                 $0.0105

📊 Sesión acumulada
   Total tokens: 18.400   →  $0.087
   Workers API:            →  $0.000  (corrieron en suscripción)
─────────────────────────────
```

En Telegram el bloque es colapsable (botón "Ver consumo") para no ensuciar la conversación. En Web UI es un panel lateral siempre visible.

### Qué trackea el backend por cada turno

En la tabla `messages`:
- `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`
- `model`
- `cost_usd` (calculado en el backend con los precios de la tabla de arriba)

En la tabla `workers`:
- `input_tokens`, `output_tokens`, `cost_usd` (si el worker fue via API; 0 si fue Claude Code CLI)

En la tabla `sessions`:
- `total_cost_usd` (acumulado de todos los mensajes de la sesión)

### Panel de costos en Web UI

Una vista dedicada `/costs` con:
- Costo del día / semana / mes
- Desglose por agente (orquestador vs sub-agentes)
- Desglose por modelo (Sonnet vs Haiku vs Opus)
- Gráfico de evolución diaria
- Proyección mensual basada en la última semana

---

## 5. Web UI — panel de control completo

La Web UI no es solo un chat. Es el **centro de operaciones del sistema**.

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  HEADER: estado del sistema  |  costos del día  |  alerts       │
├──────────┬──────────────────────────────┬────────────────────────┤
│          │                              │                        │
│ SIDEBAR  │      CHAT PRINCIPAL          │   PANEL DERECHO        │
│          │                              │                        │
│ Sesiones │  Conversación con el         │  [Tab: Equipo]         │
│ pasadas  │  orquestador, streaming SSE  │  [Tab: Traces]         │
│          │                              │  [Tab: Memoria]        │
│ Notion   │  Eventos inline del equipo:  │  [Tab: Costos]         │
│ boards   │  • Worker creado             │  [Tab: Notion]         │
│          │  • Worker terminó            │                        │
│ Filtros  │  • Sub-agente activo         │                        │
│          │  • Approval needed           │                        │
│          │                              │                        │
│          │  Footer: consumo del turno   │                        │
└──────────┴──────────────────────────────┴────────────────────────┘
```

### Tab "Equipo" — el más importante

Muestra el estado de todos los agentes y workers en tiempo real:

```
EQUIPO  [actualizado hace 3s]

┌─ ORQUESTADOR ────────────────────────────────┐
│  Estado: 🟢 Activo                           │
│  Modelo: Sonnet 4.6                          │
│  Sesión actual: "Migración DB" (18 min)      │
│  Tokens sesión: 18.400  |  Costo: $0.087     │
└──────────────────────────────────────────────┘

┌─ SUB-AGENTES ────────────────────────────────┐
│                                              │
│  sub_db_migration  🔄 RUNNING  [14 min]      │
│  Objetivo: Migrar Postgres → MySQL           │
│  Modelo: Sonnet 4.6                          │
│  Tokens: 8.200  |  Costo API: $0.031         │
│  Workers: 3 completados, 1 en curso          │
│  [▼ Ver árbol de workers]                    │
│                                              │
│  sub_analista  ⚪ LIBRE                      │
│  Último trabajo: hace 2h                     │
│  [Ver historial]                             │
│                                              │
└──────────────────────────────────────────────┘

┌─ WORKERS CLAUDE CODE ────────────────────────┐
│                                              │
│  ✅ "Analizá schema actual"     2 min  done  │
│  ✅ "Generá script migración"   5 min  done  │
│  🔄 "Ejecutá migración staging" 9 min  run   │
│     └─ [Ver output en vivo]                  │
│  ⏳ "Corré tests validación"         pending │
│                                              │
│  💻 "Analizá dead code ~/api"   3 min  done  │
│     └─ 12 funciones sin uso encontradas      │
│                                              │
└──────────────────────────────────────────────┘

┌─ CONSUMO DEL EQUIPO (hoy) ───────────────────┐
│  Orquestador:    $0.087  (Sonnet)            │
│  sub_db_mig:     $0.031  (Sonnet)            │
│  sub_analista:   $0.012  (Sonnet, mañana)    │
│  Watchers:       $0.003  (Haiku)             │
│  Workers CC:     $0.000  (suscripción)       │
│  ─────────────────────────────               │
│  TOTAL HOY:      $0.133                      │
│  Proyección mes: $4.00                       │
└──────────────────────────────────────────────┘
```

### Tab "Notion" — tableros conectados

Vista de las tareas de Notion con etiqueta CLAUDE CODE o CLAUDE ANALISTA:

```
NOTION BOARDS

┌─ Tablero: "Sprint Backend" ──────────────────┐
│                                              │
│  CLAUDE CODE (3 tareas)                      │
│  ┌──────────────────────────────────────┐   │
│  │ [✅] Refactor auth module            │   │
│  │      Asignado a: CC Session          │   │
│  │      Completado hace 1h              │   │
│  │      [Ver log completo]              │   │
│  ├──────────────────────────────────────┤   │
│  │ [🔄] Migración DB Postgres→MySQL     │   │
│  │      Asignado a: sub_db_migration    │   │
│  │      En progreso — 14 min            │   │
│  │      Última actualización: hace 2min │   │
│  ├──────────────────────────────────────┤   │
│  │ [⏳] Implementar rate limiting       │   │
│  │      Sin asignar — en cola           │   │
│  │      [Asignar ahora]                 │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  CLAUDE ANALISTA (2 tareas)                  │
│  ┌──────────────────────────────────────┐   │
│  │ [⏳] Analizar logs de errores Q2     │   │
│  │      Sin asignar                     │   │
│  ├──────────────────────────────────────┤   │
│  │ [⏳] Revisar performance endpoints   │   │
│  │      Sin asignar                     │   │
│  └──────────────────────────────────────┘   │
└──────────────────────────────────────────────┘
```

### Eventos SSE del backend al frontend

```
text_delta          — fragmento de texto del orquestador
tool_use_start      — el orquestador llamó una tool
tool_use_result     — resultado de la tool
worker_created      — nuevo worker creado
worker_status       — cambio de estado (pending/running/done/failed)
worker_output_chunk — fragmento de output de Claude Code (streaming)
worker_summary      — result_summary generado al terminar
subagent_created    — nuevo sub-agente instanciado
subagent_status     — cambio de estado del sub-agente
memory_updated      — orquestador actualizó memoria
approval_needed     — acción pausada esperando confirmación
notion_task_updated — tarea de Notion fue actualizada por un agente
cost_update         — update de consumo (al final de cada turno)
done                — turno terminado
```

---

## 6. Integración con Notion — tableros etiquetados como fuente de tareas

### Cómo funciona

Yo tengo tableros en Notion con tareas. Cada tarea puede tener una de estas etiquetas (property de tipo Select o Multi-select):

- **`CLAUDE CODE`**: tarea técnica que va a una Claude Code session o sub-agente de desarrollo.
- **`CLAUDE ANALISTA`**: tarea de análisis/investigación que va al sub-agente analista.

Cuando le pido al orquestador que trabaje sobre las tareas de un tablero, él:

1. Consulta Notion vía MCP y lee todas las tareas con esas etiquetas en el tablero indicado.
2. Clasifica cada tarea: `CLAUDE CODE` → `run_claude_code` o `sub_dev`; `CLAUDE ANALISTA` → `sub_analista`.
3. Asigna las tareas a los agentes correspondientes (o las encola si hay límite de workers activos).
4. A medida que trabaja, **actualiza la tarea en Notion** con el progreso.
5. Al terminar, marca la tarea como completada en Notion y adjunta el resultado.

### Actualizaciones de Notion durante el trabajo

Cada tarea en Notion recibe updates automáticos mientras el agente trabaja:

**Al asignar:**
```
Status: En progreso
Asignado a: sub_db_migration
Iniciado: 2026-05-19 14:32
```

**Durante el trabajo (cada N minutos o al terminar una fase):**
```
Progreso: [████░░░░] 50%
Última actualización: 14:45
Log: Fase 1 completada — schema analizado (8 tablas).
     Fase 2 en curso — generando scripts de migración.
```

**Al terminar:**
```
Status: Completado ✅
Completado: 2026-05-19 15:01
Duración: 29 min
Resultado: Migración exitosa. 23 tablas, 0 errores.
           Tests pasando en staging.
Tokens consumidos: 12.400 | Costo: $0.047
[Ver log completo] [link al output]
```

### Capturas de pantalla

Si yo pido explícitamente capturas ("actualizá la tarea con capturas"), el agente usa `computer_use` para tomar screenshots del estado de la terminal o de la app, y los adjunta a la tarea de Notion como imágenes. Esto es opt-in por tarea (no el default, porque `computer_use` es caro).

Para activarlo:
```
Yo: "trabajá en las tareas del tablero Sprint Backend y actualizá con capturas"
Orquestador: "¿Confirmás que querés capturas? Activa computer_use (~$0.05 extra por tarea)"
[✓ Sí] [✗ No, solo texto]
```

### Cómo pedirle al orquestador que trabaje en las tareas

```
Yo: "trabajá en las tareas pendientes del tablero Sprint Backend"
→ Orquestador lee tablero, lista las tareas con etiquetas, confirma asignación

Yo: "ejecutá solo las tareas de CLAUDE CODE del tablero"
→ Filtra por etiqueta, asigna solo esas

Yo: "ejecutá la tarea 'Migración DB' del tablero Sprint Backend"
→ Busca esa tarea específica, la asigna al agente correcto

Yo: "qué tareas hay pendientes para mí en los tableros?"
→ Lista todas las tareas sin etiqueta Claude (las que son para vos)
```

### Tableros configurables

En el `.env` o en memoria del orquestador se definen los tableros "autorizados":

```
NOTION_WATCHED_BOARDS=["Sprint Backend", "Proyectos 2026", "Investigación"]
```

El orquestador solo mira esos tableros. No accede a todo Notion sin que vos lo hayas configurado.

---

## 7. Sub-agentes — cómo se crean y qué permisos tienen

### Qué es un sub-agente

No es una entidad permanente. Es una **configuración instanciada bajo demanda** por el orquestador cuando la tarea lo justifica. Tiene su propio loop agéntico, puede lanzar múltiples workers de Claude Code, y le reporta al orquestador (no al usuario directamente).

**La diferencia con un worker de Claude Code:**

| | Worker Claude Code | Sub-agente |
|---|---|---|
| Autonomía | Ejecuta un prompt y termina | Loop propio, toma decisiones |
| Workers propios | No aplica | Puede lanzar N workers CC |
| Duración | Minutos | Minutos a horas |
| Costo | Suscripción | API (Sonnet 4.6) |

### Tipos de sub-agentes predefinidos

```python
SUB_AGENTS = {
    "sub_dev": {
        "descripcion": "Desarrollo de software: refactors, features, migraciones",
        "modelo": "claude-sonnet-4-6",
        "tools": ["run_claude_code", "read_file", "web_search", "notion_update"],
        "forbidden": ["send_email", "delete_database"],
        "max_workers": 5,
        "approval_policy": "confirm_writes",
    },
    "sub_analista": {
        "descripcion": "Análisis de datos, logs, código, documentación",
        "modelo": "claude-sonnet-4-6",
        "tools": ["run_claude_code", "read_file", "web_search", "notion_update"],
        "forbidden": ["write_file", "delete_file"],
        "max_workers": 3,
        "approval_policy": "auto",  # solo lectura, no necesita confirmación
    },
}
```

El orquestador puede crear sub-agentes de estos tipos con contexto específico para la tarea. En el futuro, podés agregar más tipos a este diccionario.

### Cómo se crean en runtime

El orquestador llama la tool `create_subagent`:

```python
create_subagent(
    type="sub_dev",
    name="sub_db_migration",      # nombre descriptivo para la UI
    objective="Migrar DB Postgres → MySQL en ~/proyecto",
    context={"working_dir": "~/proyecto", "staging_url": "..."},
    notion_task_id="abc123",       # para que actualice la tarea al terminar
    notify_on_done=True
)
```

### Permisos en la UI

En la Web UI, cada sub-agente tiene su propio panel de permisos expandible:

```
sub_db_migration  [editar permisos]
  ✅ run_claude_code
  ✅ read_file
  ✅ web_search
  ✅ notion_update
  ❌ send_email (bloqueado)
  ❌ delete_database (bloqueado)
  Política: confirm_writes
  Workers activos: 1/5
  Timeout: 60 min
```

Desde la UI podés revocar permisos en runtime o forzar cancelación.

---

## 8. Arquitectura completa

```
╔══════════════════════════════════════════════════════════════════╗
║                           YO                                     ║
╚══════════════╤════════════════════════════════╤══════════════════╝
               │                                │
               ▼                                ▼
    ┌──────────────────┐              ┌─────────────────────────┐
    │    Telegram      │              │        Web UI           │
    │                  │              │      (Next.js)          │
    │  Chat + botones  │              │                         │
    │  inline + notif  │              │  Chat + Panel Equipo    │
    │  Consumo por msg │              │  Workers árbol + Notion │
    │                  │              │  Costos + Memoria       │
    └────────┬─────────┘              └────────────┬────────────┘
             │ webhook                             │ HTTP/SSE
             └─────────────────┬───────────────────┘
                               ▼
╔═════════════════════════════════════════════════════════════════╗
║                   BACKEND (FastAPI + Python)                    ║
║                                                                 ║
║  ┌─────────────────────────────────────────────────────────┐   ║
║  │              ORQUESTADOR (Sonnet 4.6)                   │   ║
║  │  System prompt + memoria inyectada + confirm_writes     │   ║
║  │  Footer automático: tokens + costo en cada mensaje      │   ║
║  │                                                         │   ║
║  │  Tools: get/update_memoria, run_claude_code,            │   ║
║  │         get_workers_status, cancel_worker,              │   ║
║  │         create_subagent, MCP:Notion, web_search         │   ║
║  └─────────────────────────────────────────────────────────┘   ║
║                                                                 ║
║  WorkerManager  │  SubAgentRegistry  │  NotionTaskSync         ║
║  CostTracker    │  MemoryService     │  ScreenshotService      ║
║                                                                 ║
║  Celery workers (ejecución de Claude Code sessions)            ║
║  Sessions │ Messages │ Memory │ Workers │ Costs │ Traces (PG) ║
╚═════════════════════════════════════════════════════════════════╝
                               │
          ┌────────────────────┼──────────────────────┐
          ▼                    ▼                      ▼
  ┌──────────────┐   ┌──────────────────┐   ┌───────────────────┐
  │ Claude Code  │   │   Sub-agentes    │   │   MCP: Notion     │
  │  Sessions    │   │  (Sonnet 4.6)    │   │   Gmail, Calendar │
  │ (suscripción)│   │  (API billing)   │   │   (oficial remoto)│
  └──────────────┘   └──────────────────┘   └───────────────────┘
```

---

## 9. Plan de implementación por fases

### 🔲 Fase 1 — Orquestador + Telegram + Workers + Costos (MVP)

**Criterio de éxito**: decirle al orquestador "hacé X", que lance Claude Code, monitoree, y al terminar me avise por Telegram con resultado + costo. Y que cada mensaje incluya el consumo.

Tareas:
1. Docker Compose: postgres, redis, backend, worker Celery.
2. Modelos DB: sessions, messages (con cost_usd), workers, memory, pending_approvals, tool_traces.
3. `CostTracker`: calcula costo por turno según tokens y modelo. Agrega footer al response.
4. `MemoryService`, `WorkerManager`.
5. `ToolRegistry`: memoria + `run_claude_code` + `get_workers_status` + `cancel_worker`.
6. `AgentRunner`: loop + memoria + confirm_writes + footer de costo automático.
7. Celery task `execute_claude_code`: subprocess + captura output + update worker.
8. `AgentConfig` orquestador: Sonnet 4.6 + MCP Notion + tools.
9. Endpoints: `/api/chat`, `/api/sessions`, `/api/memory`, `/api/workers`, `/api/approvals`, `/api/costs`.
10. Telegram adapter: webhook + cliente + botones + footer consumo colapsable.
11. Hook Claude Code → `scripts/notify_stop.py` → POST backend.
12. Test: "analizá dead code en ~/proyecto" → worker → notif → resultado + costo en Telegram.

### 🔲 Fase 2 — Web UI (panel de control completo)

- Next.js (App Router, Tailwind, shadcn/ui).
- Chat con SSE.
- Tab "Equipo": árbol de workers en tiempo real, estado de sub-agentes, costos del día.
- Tab "Notion": vista de tableros etiquetados con estado de tareas.
- Tab "Costos": desglose por agente, modelo, proyección mensual.
- Tab "Memoria", "Traces".
- Todos los eventos SSE de la sección 5.

### 🔲 Fase 3 — Integración Notion como fuente de tareas

- Tool `notion_get_tasks_by_label(board, label)`: lee tareas etiquetadas.
- Tool `notion_update_task(task_id, progress, log, status)`: actualiza tarea con progreso.
- Tool `notion_attach_screenshot(task_id, image)`: adjunta captura (opt-in).
- Lógica de asignación: CLAUDE CODE → `run_claude_code`/`sub_dev`; CLAUDE ANALISTA → `sub_analista`.
- Config `NOTION_WATCHED_BOARDS` en `.env`.
- Flujo de confirmación antes de ejecutar batch de tareas.
- Actualización automática al terminar cada worker.

### 🔲 Fase 4 — Sub-agentes especializados

- `SubAgentRegistry` con `sub_dev` y `sub_analista`.
- Tool `create_subagent` en el orquestador.
- Sub-agentes con su propio loop, workers con `parent_id`.
- Panel de permisos en Web UI (editable en runtime).
- `ScreenshotService` para capturas opt-in.

### 🔲 Fase 5 — Gmail + Calendar + Watchers

- MCP Gmail y Calendar.
- `mail_watcher` con Haiku 4.5 (cron 15 min).
- `calendar_watcher` con Haiku 4.5 (cron 30 min).
- Watchers inyectan al orquestador como si fuera el usuario.

### 🔲 Fase 6 — MCP servers internos

Cuando aparezca un sistema interno concreto que justifique conectar.

---

## 10. Estructura del repo

```
claude-agents/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
│
├── scripts/
│   └── notify_stop.py           # Hook Claude Code → POST backend
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── config.py            # settings + NOTION_WATCHED_BOARDS
│       ├── worker.py            # Celery app
│       │
│       ├── agents/
│       │   ├── config.py        # AgentConfig orquestador + SUB_AGENTS dict
│       │   └── runner.py        # Loop + memoria + footer costo automático
│       │
│       ├── costs/
│       │   └── tracker.py       # CostTracker: calcula y formatea footer
│       │
│       ├── workers/
│       │   ├── manager.py       # WorkerManager
│       │   └── tasks.py         # Celery: execute_claude_code
│       │
│       ├── notion/
│       │   ├── task_sync.py     # Lee y actualiza tareas etiquetadas
│       │   └── screenshots.py   # ScreenshotService (opt-in)
│       │
│       ├── memory/
│       │   └── service.py
│       │
│       ├── tools/
│       │   └── registry.py
│       │
│       ├── telegram/
│       │   ├── webhook.py
│       │   ├── client.py
│       │   └── buttons.py
│       │
│       ├── api/
│       │   ├── routes.py        # + /api/costs
│       │   ├── schemas.py
│       │   └── deps.py
│       │
│       └── db/
│           ├── models.py
│           └── session.py
│
└── frontend/                    # (Fase 2) Next.js
```

---

## 11. Modelos de datos

### `sessions`
`id`, `agent_id`, `title`, `channel` ("telegram"|"web"), `external_chat_id`, `total_cost_usd`, `created_at`, `updated_at`

### `messages`
`id`, `session_id`, `position`, `role`, `content` (JSONB), `model`, `stop_reason`
`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `cost_usd`
`created_at`

### `workers`
`id`, `parent_id` (FK self, nullable), `agent_id`, `session_id`, `type` ("claude_code"|"subagent")
`status` (pending|running|waiting_input|done|failed|cancelled)
`prompt`, `working_dir`, `output` (text), `result_summary`
`input_tokens`, `output_tokens`, `cost_usd` (0 si fue CC suscripción)
`notion_task_id` (nullable), `screenshots` (JSONB array, nullable)
`error`, `notified`, `created_at`, `started_at`, `finished_at`

### `memory`
`id`, `key`, `value` (JSONB), `category`, `created_at`, `updated_at`

### `pending_approvals`
`id`, `session_id`, `tool_use_id`, `tool_name`, `tool_input` (JSONB)
`status` (pending|approved|rejected|edited), `edited_input` (JSONB)
`created_at`, `resolved_at`

### `daily_costs`
`id`, `date`, `agent_id`, `model`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cost_usd`
(agregado diario para el dashboard de costos)

### `tool_traces`
`id`, `session_id`, `tool_name`, `tool_input`, `tool_output`, `error`, `duration_ms`, `created_at`

---

## 12. Footer de costo — implementación

El `AgentRunner` calcula y agrega el footer al final de cada respuesta del orquestador:

```python
# costs/tracker.py
PRICES = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
    "claude-haiku-4-5":  {"input": 1.0, "output":  5.0, "cache_read": 0.1},
    "claude-opus-4-7":   {"input": 5.0, "output": 25.0, "cache_read": 0.5},
}

def calculate_cost(model, input_tok, output_tok, cache_read_tok, cache_write_tok) -> float:
    p = PRICES[model]
    return (
        input_tok      * p["input"]      / 1_000_000 +
        output_tok     * p["output"]     / 1_000_000 +
        cache_read_tok * p["cache_read"] / 1_000_000
    )

def format_footer(turn_cost, session_cost, usage) -> str:
    saved = usage.input_tokens * PRICES[model]["input"] / 1_000_000 - \
            usage.cache_read_tokens * PRICES[model]["cache_read"] / 1_000_000
    return f"""
─────────────────────────────
💬 Este mensaje
   Input:  {usage.input_tokens:,} tok → ${usage.input_tokens * ... :.4f}
   Output: {usage.output_tokens:,} tok → ${...:.4f}
   Cache:  {usage.cache_read_tokens:,} tok → ${...:.4f} (ahorro: ${saved:.4f})
   Subtotal: ${turn_cost:.4f}

📊 Sesión: ${session_cost:.4f} acumulado
─────────────────────────────"""
```

En Telegram el footer va en un mensaje separado colapsado. En Web UI es el panel de "Costos" siempre visible.

---

## 13. Endpoints HTTP

Auth: `Authorization: Bearer <APP_AUTH_TOKEN>` en todos excepto `/telegram/webhook` y `/health`.

| Método | Path | Descripción |
|---|---|---|
| GET | `/health` | Healthcheck |
| POST | `/telegram/webhook` | Entrada Telegram |
| POST | `/api/chat` | Chat sincrónico |
| POST | `/api/chat/stream` | (Fase 2) SSE |
| GET | `/api/agents` | Lista agentes + sub-agentes |
| GET | `/api/sessions` | Lista sesiones |
| GET | `/api/sessions/{id}/messages` | Mensajes |
| DELETE | `/api/sessions/{id}` | Borra sesión |
| GET | `/api/memory` | Lista memoria |
| POST | `/api/memory` | Upsert |
| DELETE | `/api/memory/{id}` | Borra |
| GET | `/api/workers` | Lista workers (filtros: status, agent, parent) |
| GET | `/api/workers/{id}` | Detalle + output |
| POST | `/api/workers/{id}/cancel` | Cancela |
| POST | `/api/workers/{id}/hook` | Recibe hook de Claude Code |
| GET | `/api/approvals` | Lista pendientes |
| POST | `/api/approvals/{id}` | Resuelve |
| GET | `/api/costs/summary` | Resumen día/semana/mes |
| GET | `/api/costs/breakdown` | Desglose por agente y modelo |
| GET | `/api/notion/boards` | Tableros configurados + tareas etiquetadas |
| POST | `/api/notion/sync` | Fuerza sync de tableros |

---

## 14. Setup inicial

### Bot de Telegram
1. `@BotFather` → `/newbot` → `TELEGRAM_BOT_TOKEN`
2. `getUpdates` → tu `chat.id` → `TELEGRAM_ALLOWED_CHAT_ID`
3. Secret random → `TELEGRAM_WEBHOOK_SECRET`

### Notion
1. https://www.notion.so/profile/integrations → nueva "Internal" → `NOTION_API_TOKEN`
2. En cada tablero a monitorear: "..." → "Add connections" → tu integration.
3. En `.env`: `NOTION_WATCHED_BOARDS=["Sprint Backend", "Proyectos 2026"]`
4. En cada tarea: agregar property `Agente` (Select) con opciones `CLAUDE CODE` y `CLAUDE ANALISTA`.

### Anthropic API key
https://console.anthropic.com → API Keys → `ANTHROPIC_API_KEY`

### Claude Code CLI
```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

### Hook de Claude Code
En `~/.claude/settings.json`:
```json
{
  "hooks": {
    "Stop": [{"matcher": "", "hooks": [
      {"type": "command", "command": "python /ruta/claude-agents/scripts/notify_stop.py"}
    ]}]
  }
}
```

### Webhook Telegram (dev local)
```bash
ngrok http 8000
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://xxx.ngrok.io/telegram/webhook&secret_token=<SECRET>"
```

---

## 15. Comandos útiles

```bash
docker compose up --build
docker compose logs -f backend
docker compose logs -f worker
docker compose restart backend
docker compose down -v
docker compose exec backend bash
docker compose exec postgres psql -U agents -d agents

# Workers activos
SELECT id, type, status, agent_id, prompt, cost_usd FROM workers
  WHERE status IN ('running','pending') ORDER BY created_at DESC;

# Costos hoy
SELECT agent_id, model, SUM(cost_usd) FROM daily_costs
  WHERE date = CURRENT_DATE GROUP BY agent_id, model;

# Costos por sesión
SELECT s.title, s.total_cost_usd FROM sessions s ORDER BY s.created_at DESC LIMIT 10;

# Consumo de tokens por modelo
SELECT model, SUM(input_tokens), SUM(output_tokens), SUM(cache_read_tokens), SUM(cost_usd)
  FROM messages GROUP BY model;

# Tareas de Notion en proceso
SELECT id, notion_task_id, status, cost_usd FROM workers
  WHERE notion_task_id IS NOT NULL ORDER BY created_at DESC;
```

---

## 16. Cosas a NO hacer

- **No usar Haiku para el orquestador ni sub-agentes.** Haiku solo para watchers, clasificación, y resúmenes de workers. Sonnet es el mínimo para tool use agéntico.
- **No usar Opus como default.** Solo para escalado puntual explícito.
- **No implementar Cowork.** Descartado definitivamente.
- **No multi-tenant ni roles.**
- **No framework de agentes** (LangChain, etc.). Loop son ~200 líneas con SDK.
- **No sub-agentes en Fase 1.** Orquestador + Claude Code directo para el MVP.
- **No capturas por default.** `computer_use` es opt-in por tarea, siempre con confirmación.
- **No acceder a tableros de Notion no configurados en `NOTION_WATCHED_BOARDS`.**
- **No Web UI en Fase 1.** Telegram primero.

---

## 17. Conversaciones típicas

**Ejecutar tareas de Notion:**
> Yo: trabajá en las tareas pendientes del tablero "Sprint Backend"
> Orquestador: Encontré 3 tareas con etiqueta CLAUDE CODE y 2 con CLAUDE ANALISTA. ¿Las arranco todas o querés revisar primero?
> [▶ Arrancar todas] [📋 Ver lista] [✗ Cancelar]

**Status del equipo:**
> Yo: cómo va el equipo?
> Orquestador: sub_db_migration corriendo hace 14 min (fase 2/4). CC "dead code" terminó — 12 funciones encontradas. sub_analista está libre. Costo acumulado hoy: $0.13.

**Asignación con capturas:**
> Yo: ejecutá la tarea "Deploy a staging" y actualizá Notion con capturas
> Orquestador: ⚠️ Las capturas activan computer_use (~$0.05 extra por tarea). ¿Confirmás?
> [✓ Sí con capturas] [📝 Solo texto] [✗ Cancelar]

**Footer de consumo (al final de cada respuesta):**
> ...respuesta del orquestador...
> ─────────────────────────
> 💬 Este mensaje: $0.011 (1.240 in / 380 out / 3.800 cache)
> 📊 Sesión total: $0.087

**Crear sub-agente desde cero:**
> Yo: la migración de DB es muy grande, creá un sub-agente para manejarla
> Orquestador: Instanciando sub_dev para "Migración DB Postgres → MySQL". Va a coordinar hasta 5 Claude Code sessions. Política: confirm antes de escribir en producción.
> ✓ sub_db_migration creado. Empezó el análisis del schema.

---

## 18. Cómo trabajar con Claude Code sobre este proyecto

Guardá como `CLAUDE.md` en la raíz del repo.

**Pedidos bien formulados:**
- *"Implementá Fase 1 completa: secciones 10, 11 y 12 del documento."*
- *"Implementá el CostTracker y el footer automático (sección 12)."*
- *"Implementá NotionTaskSync: leer tareas etiquetadas y actualizar progreso (sección 6)."*
- *"Implementá el Tab Equipo de la Web UI con árbol de workers en tiempo real (sección 5)."*

**Convenciones:**
- Type hints obligatorios. Async por default. Pydantic v2.
- Docstrings en castellano para lógica de negocio.
- Imports: stdlib → third-party → app.

---

## 19. Glosario

- **Orquestador**: agente principal, Sonnet 4.6. Único punto de contacto con el usuario.
- **Sub-agente**: agente Nivel 1 instanciado bajo demanda. Loop propio, lanza workers CC. Sonnet 4.6.
- **Worker**: unidad de trabajo registrada en DB. Puede ser Claude Code session o sub-agente.
- **Claude Code session**: ejecutor técnico. Recibe prompt + dir, corre, devuelve output. Suscripción.
- **WorkerManager**: módulo de CRUD y estado de workers.
- **CostTracker**: calcula costo por turno y formatea el footer de consumo.
- **NotionTaskSync**: lee tareas etiquetadas y actualiza su estado/progreso en Notion.
- **CLAUDE CODE / CLAUDE ANALISTA**: etiquetas en propiedades de Notion que definen a qué agente va la tarea.
- **Footer de costo**: bloque al final de cada mensaje con tokens consumidos y costo en USD.
- **Sesión**: conversación persistida. Tiene `total_cost_usd` acumulado.
- **Memoria**: tabla de contexto del usuario, separada del historial. Inyectada en el system prompt.
- **confirm_writes**: política que pausa antes de tools con `requires_confirmation=True`.
- **Loop agéntico**: bucle api_call → tool_use → execute → tool_result hasta que el modelo termina.

---

*Última actualización: política de modelos por nivel (Haiku para periféricos, Sonnet para orquestador y sub-agentes, Opus puntual). Footer de consumo automático en cada mensaje. Web UI redefinida como panel de control completo con tab Equipo, tab Notion, tab Costos. Integración con tableros de Notion etiquetados como fuente de tareas con actualización automática de progreso y capturas opt-in.*

---

## 20. Seguridad del sistema

Ver documento completo: **`SECURITY.md`**

### Resumen de las capas de seguridad

El sistema tiene tres capas de defensa independientes:

**Capa 1 — System prompt de cada agente**
Cada agente tiene al final de su system prompt las reglas de seguridad del
documento SECURITY.md sección 10. El modelo sabe que el contenido externo
son datos, no instrucciones, y sabe qué patrones ignorar.

**Capa 2 — Validaciones en el backend (código)**
Antes de ejecutar cualquier tool call, el `AgentRunner` valida:
- ¿La tool está en la lista permitida del agente?
- ¿El directorio/recurso está autorizado?
- ¿No se superó el rate limit de la tool?
- ¿No se superó el límite de costo diario/por sesión?
El output de cada tool se sanitiza buscando patrones de injection antes
de pasarlo al modelo.

**Capa 3 — Notificaciones al usuario**
Eventos de seguridad `warning` o `critical` notifican por Telegram
inmediatamente con botones para detener el agente o continuar.
La Web UI tiene un panel de eventos de seguridad con historial.

### El vector más importante: agente de Chrome

Cuando se implemente el agente de Chrome (futuro), aplican reglas adicionales:
- Lista blanca de dominios en `CHROME_ALLOWED_DOMAINS` (no hay excepciones)
- Todo el contenido de la página es DATOS, nunca instrucciones
- Texto oculto (blanco sobre blanco, display:none) también se sanitiza
- Popups de permisos del browser siempre bloqueados
- Screenshots ante contenido sospechoso + notificación al usuario

### Variables de seguridad en `.env`

```bash
ALLOWED_WORKING_DIRS=["/home/user/proyectos"]
NOTION_WATCHED_BOARDS=["Sprint Backend"]
CHROME_ALLOWED_DOMAINS=["github.com"]   # cuando se implemente
MAX_COST_PER_SESSION_USD=5.0
MAX_COST_PER_DAY_USD=20.0
SECURITY_STRICT_MODE=true               # pausa todo ante injection detectada
SECURITY_NOTIFY_LEVEL=warning
```

---

## 21. Router inteligente — optimización de tokens y costos

### El problema

Sin routing, cada mensaje carga el contexto completo del orquestador: system prompt + memoria + todas las tool definitions + historial. Son ~8.000 tokens de contexto fijos por mensaje, sin importar si preguntás "qué hora es" o "migrá toda la DB".

### La solución: router liviano previo

Antes de que el orquestador procese cualquier mensaje, un call barato a Haiku 4.5 clasifica el mensaje y decide exactamente qué cargar.

```
Mensaje → Router (Haiku, ~200 tok, $0.0002) → JSON de clasificación
                                                       │
                              ┌────────────────────────┼──────────────────────────┐
                              ▼                        ▼                          ▼
                     complexity=low           complexity=medium          complexity=high
                     Haiku responde           Sonnet + contexto          Sonnet/Opus +
                     directo                  filtrado del dominio       contexto completo
                     ~600 tok total           ~3.200 tok total           ~8.000 tok total
                     ahorro ~92%              ahorro ~60%                sin ahorro
```

### JSON que devuelve el router

```python
ROUTER_SYSTEM = """
Clasificás mensajes del usuario. Devolvés solo JSON, sin texto extra.
{
  "category": "consulta_simple|notion_tasks|coding|admin_email|admin_calendar|analisis|arquitectura",
  "complexity": "low|medium|high",
  "tools_needed": ["run_claude_code", "notion_get_tasks"],  # solo las necesarias
  "memory_categories": ["proyecto", "preferencia"],         # solo categorías relevantes
  "suggested_model": "haiku|sonnet|opus"
}
"""
```

### Lógica del AgentRunner con routing

```python
async def run_with_routing(self, message: str, session_id: str) -> RunResult:
    # 1. Router: call barato a Haiku
    route = await self.router.classify(message)

    # 2. Camino low: Haiku responde directo, sin orquestador
    if route.complexity == "low":
        return await self.run_direct_haiku(message, session_id)

    # 3. Caminos medium/high: orquestador con contexto filtrado
    agent = self.build_filtered_agent(
        base_agent=ORCHESTRATOR,
        tools=route.tools_needed,           # subset de tools
        memory_categories=route.memory_categories,  # subset de memoria
        model=route.suggested_model,
    )
    return await self.run(agent, session_id, message)
```

### Contexto que se carga por dominio (medium complexity)

| Categoría | Tools cargadas | Memoria cargada | Tokens ctx |
|---|---|---|---|
| `consulta_simple` | ninguna | nota_libre | ~600 |
| `notion_tasks` | notion_*, run_claude_code | proyecto, objetivo_actual | ~2.800 |
| `coding` | run_claude_code, create_subagent | proyecto | ~2.400 |
| `admin_email` | gmail_*, calendar_* | preferencia, persona | ~2.600 |
| `analisis` | sub_analista, web_search | proyecto, objetivo_actual | ~3.200 |
| `arquitectura` | todos | todos | ~8.000 |

### Impacto en costos

Asumiendo distribución típica de uso personal:
- 40% mensajes `low` (consultas, resúmenes, traducciones)
- 45% mensajes `medium` (tareas de dominio específico)
- 15% mensajes `high` (arquitectura, orquestación compleja)

Ahorro promedio por mensaje: **~65% de tokens de contexto**.
En práctica: de ~$10/mes estimado sin router → ~$3.50/mes con router.

### Tabla de modelos con routing

| Nivel | Modelo | Cuándo |
|---|---|---|
| Router | Haiku 4.5 | Siempre, para todo mensaje |
| Respuesta directa | Haiku 4.5 | complexity=low |
| Orquestador filtrado | Sonnet 4.6 | complexity=medium |
| Orquestador completo | Sonnet 4.6 | complexity=high |
| Escalado puntual | Opus 4.7 | complexity=high + suggested_model=opus |

### Nueva tabla de módulos en `agents/config.py`

```python
ROUTER_CONFIG = AgentConfig(
    id="router",
    model="claude-haiku-4-5",
    system_prompt=ROUTER_SYSTEM,
    max_tokens_per_turn=256,   # solo necesita devolver JSON corto
    enable_prompt_caching=True,
)

DOMAIN_TOOL_SETS = {
    "notion_tasks":  ["run_claude_code", "notion_get_tasks", "notion_update_task", "get_memoria"],
    "coding":        ["run_claude_code", "create_subagent", "web_search", "get_memoria"],
    "admin_email":   ["gmail_mcp", "calendar_mcp", "get_memoria", "update_memoria"],
    "analisis":      ["run_claude_code", "web_search", "get_memoria"],
    "arquitectura":  None,  # None = cargar todo
}
```

### Cómo se refleja en la Web UI

El panel de costos desglosa por categoría de routing:
```
Hoy — distribución de mensajes
  low  (Haiku directo):     12 msg  ·  $0.004
  medium (Sonnet filtrado): 18 msg  ·  $0.031
  high (Sonnet completo):    3 msg  ·  $0.018
  ─────────────────────────────────────────────
  Total:                    33 msg  ·  $0.053
  Sin router hubiera sido:            $0.148
  Ahorro del router:                  $0.095  (64%)
```


---

## 22. Repositorio GitHub

```
Usuario:    lucascatro29
Email:      lucascastro2929@gmail.com
Repo:       Agente_Orquestador
URL:        https://github.com/lucascatro29/Agente_Orquestador
Directorio: /Users/lucascastro/Desktop/Lucas/lucascastro2929 Github/Agente_Orquestador
```

### Estructura de branches

```
main        — código estable, una fase completa por push grande
```

Un solo branch por ahora dado que es mono-usuario. Cuando haya más colaboradores se agrega `develop`.

### Convención de commits

Conventional commits en minúscula:
- `feat:` nueva funcionalidad
- `fix:` bug
- `chore:` infra/config
- `docs:` solo documentación
- `refactor:` sin nueva funcionalidad

