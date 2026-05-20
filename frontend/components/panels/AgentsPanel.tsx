"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Loader2, CheckCircle2, Circle, Bot, Cpu, FlaskConical } from "lucide-react";
import { getAgents, getSchedule, getScheduledTasks, toggleScheduledTask, deleteScheduledTask, type AgentEntry, type ScheduleTaskEntry, type UserScheduledTask } from "@/lib/api";

const MODEL_SHORT: Record<string, string> = {
  "claude-sonnet-4-6":         "Sonnet 4.6",
  "claude-haiku-4-5-20251001": "Haiku 4.5",
  "claude-opus-4-7":           "Opus 4.7",
};

const TYPE_LABEL: Record<string, string> = {
  orchestrator: "Orquestador",
  subagent:     "Sub-agente",
};

const TYPE_COLOR: Record<string, string> = {
  orchestrator: "border-violet-500/40 text-violet-300",
  subagent:     "border-sky-500/40 text-sky-300",
};

const AGENT_ICON: Record<string, React.ReactNode> = {
  orchestrator: <Bot className="w-3.5 h-3.5 text-violet-400" />,
  subagent:     <Cpu className="w-3.5 h-3.5 text-sky-400" />,
};

const POLICY_LABEL: Record<string, string> = {
  confirm_writes: "confirma escrituras",
  confirm_all:    "confirma todo",
  auto:           "automático",
};

function ActiveDot({ count }: { count: number }) {
  if (count === 0) return <Circle className="w-3 h-3 text-zinc-600" />;
  return <Loader2 className="w-3 h-3 text-emerald-400 animate-spin" />;
}

function AgentCard({ agent }: { agent: AgentEntry }) {
  const [expanded, setExpanded] = useState(false);
  const isActive = agent.active_workers > 0;

  return (
    <div className={`border rounded-lg p-2.5 space-y-1.5 text-xs transition-colors ${isActive ? "border-emerald-500/30 bg-emerald-500/5" : "border-zinc-800 bg-zinc-900/30"}`}>
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <ActiveDot count={agent.active_workers} />
          {AGENT_ICON[agent.type] ?? <Bot className="w-3.5 h-3.5 text-zinc-500" />}
          <span className="font-semibold truncate text-zinc-200">{agent.id}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {isActive ? (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              {agent.active_workers}w activo{agent.active_workers > 1 ? "s" : ""}
            </span>
          ) : (
            <span className="text-[10px] text-zinc-600">inactivo</span>
          )}
          <Badge variant="outline" className={`text-[10px] bg-transparent ${TYPE_COLOR[agent.type] ?? "text-zinc-500"}`}>
            {TYPE_LABEL[agent.type] ?? agent.type}
          </Badge>
        </div>
      </div>

      <div className="flex gap-3 text-zinc-500">
        <span className="text-[10px]">{MODEL_SHORT[agent.model] ?? agent.model}</span>
        <span className="text-[10px]">
          {agent.type === "orchestrator"
            ? <><span className="text-zinc-300 font-medium">{agent.total_sessions}</span> sesiones</>
            : <><span className="text-zinc-300 font-medium">{agent.total_runs}</span> ejecuciones</>}
        </span>
        {agent.max_workers != null && (
          <span className="text-[10px]">max <span className="text-zinc-300 font-medium">{agent.max_workers}</span></span>
        )}
      </div>

      <div className="text-[10px] text-zinc-600">
        🔐 {POLICY_LABEL[agent.approval_policy] ?? agent.approval_policy}
      </div>

      <button
        onClick={() => setExpanded((v) => !v)}
        className="text-[10px] text-zinc-600 hover:text-zinc-300 transition-colors"
      >
        {agent.tools.length} tools {expanded ? "▲" : "▼"}
      </button>

      {expanded && (
        <div className="flex flex-wrap gap-1 pt-0.5">
          {agent.tools.map((t) => (
            <span key={t} className="font-mono text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded border border-zinc-700/50">
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
    ? new Date(task.last_checked_at).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div className="border border-zinc-800 rounded-lg p-2.5 space-y-1 text-xs bg-zinc-900/30">
      <div className="flex items-center justify-between gap-1">
        <span className="font-semibold truncate text-zinc-300">{task.label}</span>
        <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded-full font-medium border ${task.enabled ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30" : "bg-zinc-800 text-zinc-600 border-zinc-700"}`}>
          {task.enabled ? "activo" : "inactivo"}
        </span>
      </div>
      <div className="text-[10px] text-zinc-500">⏱ {task.schedule}</div>
      {lastRun
        ? <div className="text-[10px] text-zinc-600">último: {lastRun}</div>
        : <div className="text-[10px] text-zinc-700 italic">sin ejecuciones aún</div>}
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
    <div className="border border-zinc-800 rounded-lg p-2.5 space-y-1.5 text-xs bg-zinc-900/30">
      <div className="flex items-center justify-between gap-1">
        <span className="font-semibold truncate text-zinc-200">{task.name}</span>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={handleToggle}
            className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium border transition-colors ${
              task.enabled
                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20"
                : "bg-zinc-800 text-zinc-500 border-zinc-700 hover:bg-zinc-700"
            }`}
          >
            {task.enabled ? "activo" : "inactivo"}
          </button>
          <button onClick={handleDelete} className="text-zinc-600 hover:text-red-400 transition-colors px-1" title="Eliminar">×</button>
        </div>
      </div>
      {task.description && <div className="text-[10px] text-zinc-500 truncate">{task.description}</div>}
      <div className="text-[10px] text-zinc-600">⏱ {task.cron_expr} · {task.action_type}</div>
      <div className="flex gap-3 text-[10px] text-zinc-600">
        {lastRun && <span>último: {lastRun}</span>}
        {nextRun && <span>próximo: {nextRun}</span>}
        {task.run_count > 0 && <span>{task.run_count} runs</span>}
      </div>
      {task.last_error && <div className="text-[10px] text-red-400 truncate">⚠ {task.last_error}</div>}
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

  if (loading) return <p className="text-xs text-zinc-600 p-3">Cargando…</p>;

  return (
    <div className="p-2.5 space-y-4">
      <section>
        <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-600 mb-2">Agentes</p>
        <div className="space-y-2">
          {agents.map((a) => <AgentCard key={a.id} agent={a} />)}
        </div>
      </section>

      {userTasks.length > 0 && (
        <section>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-600 mb-2">Tareas programadas</p>
          <div className="space-y-2">
            {userTasks.map((t) => <UserTaskCard key={t.id} task={t} onRefresh={load} />)}
          </div>
        </section>
      )}

      <section>
        <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-600 mb-2">Watchers sistema</p>
        <div className="space-y-2">
          {schedule.map((t) => <ScheduleCard key={t.name} task={t} />)}
        </div>
      </section>
    </div>
  );
}
