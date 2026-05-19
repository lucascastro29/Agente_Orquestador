"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { getAgents, getSchedule, type AgentEntry, type ScheduleTaskEntry } from "@/lib/api";

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

  return (
    <div className="border border-border rounded-md p-2 space-y-1 text-xs">
      {/* Header */}
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <ActiveDot count={agent.active_workers} />
          <span className="font-semibold truncate">{agent.id}</span>
        </div>
        <Badge
          variant="outline"
          className={`shrink-0 text-[10px] ${TYPE_COLOR[agent.type] ?? ""}`}
        >
          {TYPE_LABEL[agent.type] ?? agent.type}
        </Badge>
      </div>

      {/* Modelo */}
      <div className="text-muted-foreground">
        {MODEL_SHORT[agent.model] ?? agent.model}
      </div>

      {/* Stats */}
      <div className="flex gap-3 text-muted-foreground">
        <span>
          <span className="text-foreground font-medium">{agent.active_workers}</span> activos
        </span>
        <span>
          <span className="text-foreground font-medium">{agent.total_sessions}</span> sesiones
        </span>
        {agent.max_workers != null && (
          <span>max <span className="text-foreground font-medium">{agent.max_workers}</span></span>
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

export function AgentsPanel() {
  const [agents, setAgents] = useState<AgentEntry[]>([]);
  const [schedule, setSchedule] = useState<ScheduleTaskEntry[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      const [a, s] = await Promise.all([getAgents(), getSchedule()]);
      setAgents(a);
      setSchedule(s);
    } catch {
      // silencioso
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

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

      {/* Tareas programadas */}
      <section>
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
          Tareas programadas
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
