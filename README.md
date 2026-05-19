# Agente Orquestador

Sistema jerárquico de agentes Claude para uso personal. Un orquestador central coordina sub-agentes especializados y sesiones de Claude Code, accesible desde Telegram y Web UI.

## Qué hace

- Orquestador personal (Sonnet 4.6) accesible desde Telegram y browser
- Memoria persistente entre conversaciones
- Lanza y monitorea Claude Code sessions como workers
- Lee tareas de tableros Notion etiquetados y las ejecuta automáticamente
- Sub-agentes especializados para tareas complejas
- Router inteligente (Haiku 4.5) que optimiza el costo por mensaje ~65%
- Seguridad en tres capas contra prompt injection

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python + FastAPI |
| LLM | Anthropic API (Sonnet 4.6, Haiku 4.5) |
| DB | PostgreSQL + SQLAlchemy async |
| Queue | Celery + Redis |
| Frontend | Next.js + TypeScript |
| Bot | python-telegram-bot |
| Deploy local | Docker Compose |

## Estado de implementación

- [ ] Fase 0 — Infra Docker
- [ ] Fase 1 — Backend + orquestador + Telegram
- [ ] Fase 2 — Router inteligente
- [ ] Fase 3 — Web UI
- [ ] Fase 4 — Notion como fuente de tareas
- [ ] Fase 5 — Sub-agentes especializados
- [ ] Fase 6 — Gmail + Calendar + Watchers
- [ ] Fase 7 — Claude Code bridge
- [ ] Fase 8 — Agente Chrome

## Arranque rápido

```bash
cp .env.example .env
# Editá .env con tus tokens
docker compose up --build
curl http://localhost:8000/health
```

## Documentación

- `PROJECT.md` — arquitectura completa y decisiones de diseño
- `CLAUDE.md` — guía de implementación por fases para Claude Code
- `SECURITY.md` — políticas de seguridad y restricciones de todos los agentes

## Seguridad

Este sistema implementa defensa en tres capas contra prompt injection:
1. System prompt con patrones a ignorar en todos los agentes
2. Validación de tool calls en el backend antes de ejecutar
3. Notificaciones al usuario ante eventos sospechosos

Ver `SECURITY.md` para el detalle completo.
