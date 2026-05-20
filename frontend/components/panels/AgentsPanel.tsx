"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { getAgents, getSchedule, getScheduledTasks, toggleScheduledTask, deleteScheduledTask, type AgentEntry, type ScheduleTaskEntry, type UserScheduledTask } from "@/lib/api";

const MODEL_SHORT: Record<string, string> = {
  "claude-sonnet-4-6":      "Sonnet 4.6",
  "claude-haiku-4-5-20251001": "Haiku 4.5",
  "claude-opus-4-7":        "Opus 4.7",
};

const TYPE_LABEL: Record<string, string> = {
  orchestrator: "Orquestador",
  subagent:     "Sub-agente",
};

const TYPE_COLOR: Record<string, string> = {
  orchestrator: "bg-violet-100 text-violet-800",
  subagent:     "bg-sky-100 text-sky-800",
};

const POLICY_LABEL: Record<string, string> = {
  confirm_writes: "confirma escrituras",
  confirm_all:    "confirma todo",
  auto:           "automático",
};

function ActiveDot({ count }: { count: number }) {
  if (count === 0) return <span className="inline-block w-2 h-2 rounded-full bg-gray-300" />;
  return <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse" />;
}

function AgentCard({ agent }: { agent: AgentEntry }) {
  const [expanded, setExpanded] = useState(false);
  const isActive = agent.active_workers > 0;

  return (
    <div className="border border-border rounded-md p-2 space-y-1 text-xs">
      {/* Header */}
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <ActiveDot count={agent.active_workers} />
          <span className="font-semibold truncate">{agent.id}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
              isActive
                ? "bg-green-100 text-green-800"
                : "bg-gray-100 text-gray-500"
            }`}
          >
            {isActive ? `activo · ${agent.active_workers} worker${agent.active_workers > 1 ? "s" : ""}` : "inactivo"}
          </span>
          <Badge
            variant="outline"
            className={`text-[10px] ${TYPE_COLOR[agent.type] ?? ""}`}
          >
            {TYPE_LABEL[agent.type] ?? agent.type}
          </Badge>
        </div>
      </div>

      {/* Modelo */}
      <div className="text-muted-foreground">
        {MODEL_SHORT[agent.model] ?? agent.model}
      </div>

      {/* Stats */}
      <div className="flex gap-3 text-muted-foreground">
        {agent.type === "orchestrator" ? (
          <span>
            <span className="text-foreground font-medium">{agent.total_sessions}</span> sesiones
          </span>
        ) : (
          <span>
            <span className="text-foreground font-medium">{agent.total_runs}</span> ejecuciones
          </span>
        )}
        {agent.max_workers != null && (
          <span>max <span className="text-foreground font-medium">{agent.max_workers}</span> workers</span>
        )}
      </div>

      {/* Approval policy */}
      <div className="text-muted-foreground">
        🔐 {POLICY_LABEL[agent.approval_policy] ?? agent.approval_policy}
      </div>

      {/* Tools toggle */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="text-muted-foreground hover:text-foreground transition-colors"
      >
        {agent.tools.length} tools {expanded ? "▲" : "▼"}
      </button>

      {expanded && (
        <div className="flex flex-wrap gap-1 pt-1">
          {agent.tools.map((t) => (
            <span
              key={t}
              className="font-mono text-[10px] bg-muted px-1 py-0.5 rounded"
            >
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function ScheduleCard({ task }: { task: ScheduleTaskEntry }) {
  const lastRun = task.last_checked_at
    ? new Date(task.last_checked_at).toLocaleTimeString("es-AR", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  return (
    <div className="border border-border rounded-md p-2 space-y-1 text-xs">
      <div className="flex items-center justify-between gap-1">
        <span className="font-semibold truncate">{task.label}</span>
        <span
          className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
            task.enabled
              ? "bg-green-100 text-green-800"
              : "bg-gray-100 text-gray-500"
          }`}
        >
          {task.enabled ? "activo" : "inactivo"}
        </span>
      </div>
      <div className="text-muted-foreground">⏱ {task.schedule}</div>
      {lastRun ? (
        <div className="text-muted-foreground">último: {lastRun}</div>
      ) : (
        <div className="text-muted-foreground italic">sin ejecuciones aún</div>
      )}
    </div>
  );
}

function UserTaskCard({ task, onRefresh }: { task: UserScheduledTask; onRefresh: () => void }) {
  const nextRun = task.next_run_at
    ? new Date(task.next_run_at).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })
    : null;
  const lastRun = task.last_run_at
    ? new Date(task.last_run_at).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })
    : null;

  async function handleToggle() {
    await toggleScheduledTask(task.id, !task.enabled);
    onRefresh();
  }

  async function handleDelete() {
    await deleteScheduledTask(task.id);
    onRefresh();
  }

  return (
    <div className="border border-border rounded-md p-2 space-y-1 text-xs">
      <div className="flex items-center justify-between gap-1">
        <span className="font-semibold truncate">{task.name}</span>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={handleToggle}
            className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium transition-colors ${
              task.enabled
                ? "bg-green-100 text-green-800 hover:bg-green-200"
                : "bg-gray-100 text-gray-500 hover:bg-gray-200"
            }`}
          >
            {task.enabled ? "activo" : "inactivo"}
          </button>
          <button
            onClick={handleDelete}
            className="text-muted-foreground hover:text-destructive transition-colors px-1"
            title="Eliminar tarea"
          >
            ×
          </button>
        </div>
      </div>
      {task.description && (
        <div className="text-muted-foreground truncate">{task.description}</div>
      )}
      <div className="text-muted-foreground">⏱ {task.cron_expr} · {task.action_type}</div>
      <div className="flex gap-3 text-muted-foreground">
        {lastRun && <span>último: {lastRun}</span>}
        {nextRun && <span>próximo: {nextRun}</span>}
        {task.run_count > 0 && <span>{task.run_count} ejecuciones</span>}
      </div>
      {task.last_error && (
        <div className="text-red-500 truncate text-[10px]">⚠ {task.last_error}</div>
      )}
    </div>
  );
}

export function AgentsPanel({ refreshSignal = 0 }: { refreshSignal?: number }) {
  const [agents, setAgents] = useState<AgentEntry[]>([]);
  const [schedule, setSchedule] = useState<ScheduleTaskEntry[]>([]);
  const [userTasks, setUserTasks] = useState<UserScheduledTask[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      const [a, s, u] = await Promise.all([getAgents(), getSchedule(), getScheduledTasks()]);
      setAgents(a);
      setSchedule(s);
      setUserTasks(u);
    } catch {
      // silencioso
    } finally {
      setLoading(false);
    }
  }

  // Refresco periódico base
  useEffect(() => {
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  // Refresco inmediato cuando el orquestador ejecuta una tool de workers/agentes
  useEffect(() => {
    if (refreshSignal > 0) load();
  }, [refreshSignal]);

  if (loading) return <p className="text-sm text-muted-foreground p-2">Cargando agentes…</p>;

  return (
    <div className="p-2 space-y-4">
      {/* Agentes */}
      <section>
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
          Agentes
        </p>
        <div className="space-y-2">
          {agents.map((a) => (
            <AgentCard key={a.id} agent={a} />
          ))}
        </div>
      </section>

      {/* Tareas creadas por el agente */}
      {userTasks.length > 0 && (
        <section>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
            Tareas del agente
          </p>
          <div className="space-y-2">
            {userTasks.map((t) => (
              <UserTaskCard key={t.id} task={t} onRefresh={load} />
            ))}
          </div>
        </section>
      )}

      {/* Watchers del sistema */}
      <section>
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
          Watchers sistema
        </p>
        <div className="space-y-2">
          {schedule.map((t) => (
            <ScheduleCard key={t.name} task={t} />
          ))}
        </div>
      </section>
    </div>
  );
}
