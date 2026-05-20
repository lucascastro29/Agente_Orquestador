"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { X, ChevronUp, ChevronDown, Terminal, Loader2, CheckCircle2, XCircle, Clock, Pause } from "lucide-react";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

interface WorkerEntry {
  id: string;
  agent_id: string;
  type: string;
  status: string;
  prompt: string;
  output: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

function elapsed(start: string | null, end: string | null): string {
  if (!start) return "";
  const ms = new Date(end ?? new Date()).getTime() - new Date(start).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "pending":
      return <Clock className="w-3.5 h-3.5 text-yellow-400" />;
    case "running":
      return <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />;
    case "waiting_input":
      return <Pause className="w-3.5 h-3.5 text-orange-400 animate-pulse" />;
    case "done":
      return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />;
    case "failed":
      return <XCircle className="w-3.5 h-3.5 text-red-400" />;
    case "cancelled":
      return <X className="w-3.5 h-3.5 text-zinc-500" />;
    default:
      return <Clock className="w-3.5 h-3.5 text-zinc-500" />;
  }
}

const STATUS_LABEL: Record<string, string> = {
  pending: "en cola",
  running: "ejecutando",
  waiting_input: "esperando",
  done: "terminado",
  failed: "falló",
  cancelled: "cancelado",
};

const STATUS_BG: Record<string, string> = {
  pending: "border-yellow-500/30 bg-yellow-500/5",
  running: "border-blue-500/40 bg-blue-500/5",
  waiting_input: "border-orange-500/30 bg-orange-500/5",
  done: "border-emerald-500/20 bg-emerald-500/5",
  failed: "border-red-500/30 bg-red-500/5",
  cancelled: "border-zinc-700 bg-zinc-900/20",
};

function TerminalOutput({ text, error }: { text: string | null; error: string | null }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [text, error]);

  const content = error
    ? `[ERROR] ${error}`
    : text || "Esperando output…";

  return (
    <div
      ref={ref}
      className="flex-1 overflow-y-auto font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-all p-2 text-green-300/90 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-zinc-700"
    >
      {content}
    </div>
  );
}

function ConsoleCard({
  worker,
  onClose,
}: {
  worker: WorkerEntry;
  onClose: (id: string) => void;
}) {
  const isActive = worker.status === "running" || worker.status === "pending";
  const borderClass = STATUS_BG[worker.status] ?? "border-zinc-700";

  return (
    <div
      className={`flex flex-col rounded-lg border ${borderClass} bg-zinc-950 overflow-hidden min-h-0`}
      style={{ height: "260px" }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-1.5 bg-zinc-900/80 border-b border-zinc-800 shrink-0">
        <Terminal className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          <StatusIcon status={worker.status} />
          <span className="text-xs font-semibold text-zinc-200 truncate">{worker.agent_id}</span>
          <span className="text-[10px] text-zinc-500 font-mono shrink-0">{worker.id.slice(0, 6)}</span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-[10px] text-zinc-400">
            {STATUS_LABEL[worker.status] ?? worker.status}
          </span>
          {worker.started_at && (
            <span className="text-[10px] text-zinc-600">
              {elapsed(worker.started_at, worker.finished_at)}
            </span>
          )}
          {!isActive && (
            <button
              onClick={() => onClose(worker.id)}
              className="text-zinc-600 hover:text-zinc-300 transition-colors ml-1 rounded p-0.5 hover:bg-zinc-800"
              title="Cerrar consola"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Prompt preview */}
      <div className="px-3 py-1 text-[10px] text-zinc-500 truncate border-b border-zinc-800/50 shrink-0 bg-zinc-900/40">
        {worker.prompt.slice(0, 120)}
      </div>

      {/* Terminal */}
      <TerminalOutput text={worker.output} error={worker.error} />

      {/* Running indicator */}
      {isActive && (
        <div className="shrink-0 px-3 py-1 flex items-center gap-1.5 border-t border-zinc-800/50 bg-zinc-900/40">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
          <span className="text-[10px] text-zinc-500">
            {worker.status === "pending" ? "en cola…" : "procesando…"}
          </span>
        </div>
      )}
    </div>
  );
}

interface ConsolasPanelProps {
  refreshSignal?: number;
  collapsed: boolean;
  onToggle: () => void;
}

export function ConsolasPanel({ refreshSignal = 0, collapsed, onToggle }: ConsolasPanelProps) {
  const [workers, setWorkers] = useState<WorkerEntry[]>([]);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${BASE}/api/workers`, {
        headers: { Authorization: `Bearer ${TOKEN}` },
      });
      if (res.ok) {
        const data: WorkerEntry[] = await res.json();
        setWorkers(data.slice(-30).reverse());
      }
    } catch { /* silencioso */ }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 3_000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (refreshSignal > 0) load();
  }, [refreshSignal, load]);

  const handleClose = useCallback((id: string) => {
    setDismissed((prev) => new Set([...prev, id]));
  }, []);

  const visible = workers.filter((w) => !dismissed.has(w.id));
  const active = visible.filter((w) => w.status === "running" || w.status === "pending");

  return (
    <div
      className="shrink-0 border-t border-zinc-800 bg-zinc-950 flex flex-col transition-all duration-300"
      style={{ height: collapsed ? "36px" : "320px" }}
    >
      {/* Bar header */}
      <div
        className="flex items-center gap-3 px-4 h-9 shrink-0 cursor-pointer select-none hover:bg-zinc-900/50 transition-colors"
        onClick={onToggle}
      >
        <Terminal className="w-3.5 h-3.5 text-zinc-400" />
        <span className="text-xs font-semibold text-zinc-300">Consolas</span>
        {active.length > 0 && (
          <span className="flex items-center gap-1 text-[10px] text-blue-400">
            <Loader2 className="w-3 h-3 animate-spin" />
            {active.length} activa{active.length > 1 ? "s" : ""}
          </span>
        )}
        {visible.length > 0 && active.length === 0 && (
          <span className="text-[10px] text-zinc-600">{visible.length} consola{visible.length > 1 ? "s" : ""}</span>
        )}
        <div className="ml-auto text-zinc-500">
          {collapsed ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </div>
      </div>

      {/* Content */}
      {!collapsed && (
        <div className="flex-1 overflow-x-auto overflow-y-hidden px-3 pb-3">
          {visible.length === 0 ? (
            <div className="flex items-center justify-center h-full text-xs text-zinc-600 italic">
              Sin consolas activas. El orquestador las abre al lanzar sub-agentes o Claude Code.
            </div>
          ) : (
            <div
              className="grid gap-3 h-full"
              style={{
                gridTemplateColumns: `repeat(${Math.min(visible.length, 4)}, minmax(280px, 1fr))`,
              }}
            >
              {visible.map((w) => (
                <ConsoleCard key={w.id} worker={w} onClose={handleClose} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
