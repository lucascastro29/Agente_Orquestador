"use client";

import { useEffect, useRef, useState } from "react";

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

const STATUS_COLOR: Record<string, string> = {
  pending:       "bg-yellow-100 text-yellow-800",
  running:       "bg-blue-100 text-blue-800",
  waiting_input: "bg-orange-100 text-orange-800",
  done:          "bg-green-100 text-green-800",
  failed:        "bg-red-100 text-red-800",
  cancelled:     "bg-gray-100 text-gray-500",
};

function elapsed(start: string | null, end: string | null): string {
  if (!start) return "";
  const ms = new Date(end ?? new Date()).getTime() - new Date(start).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function TerminalBox({ text, error }: { text: string | null; error: string | null }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [text, error]);

  const content = error ? `[ERROR] ${error}` : (text || "(sin output aún)");

  return (
    <div
      ref={ref}
      className="bg-zinc-950 text-green-400 font-mono text-[10px] leading-relaxed rounded p-2 overflow-y-auto max-h-48 whitespace-pre-wrap break-all"
    >
      {content}
    </div>
  );
}

function WorkerCard({ worker }: { worker: WorkerEntry }) {
  const [open, setOpen] = useState(worker.status === "running" || worker.status === "pending");

  return (
    <div className="border border-border rounded-md p-2 space-y-1 text-xs">
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1.5 min-w-0">
          {(worker.status === "running" || worker.status === "pending") && (
            <span className="inline-block w-2 h-2 rounded-full bg-blue-500 animate-pulse shrink-0" />
          )}
          <span className="font-semibold truncate">{worker.agent_id}</span>
          <span className="text-muted-foreground truncate font-mono">{worker.id.slice(0, 8)}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${STATUS_COLOR[worker.status] ?? ""}`}>
            {worker.status}
          </span>
          {worker.started_at && (
            <span className="text-muted-foreground">{elapsed(worker.started_at, worker.finished_at)}</span>
          )}
        </div>
      </div>

      <div className="text-muted-foreground truncate">{worker.prompt.slice(0, 80)}</div>

      <button
        onClick={() => setOpen((v) => !v)}
        className="text-muted-foreground hover:text-foreground transition-colors text-[10px]"
      >
        {open ? "▲ ocultar output" : "▼ ver output"}
      </button>

      {open && <TerminalBox text={worker.output} error={worker.error} />}
    </div>
  );
}

export function ConsolasPanel({ refreshSignal = 0 }: { refreshSignal?: number }) {
  const [workers, setWorkers] = useState<WorkerEntry[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      const res = await fetch(`${BASE}/api/workers`, {
        headers: { Authorization: `Bearer ${TOKEN}` },
      });
      if (res.ok) {
        const data: WorkerEntry[] = await res.json();
        // Mostrar últimos 20, más recientes primero
        setWorkers(data.slice(-20).reverse());
      }
    } catch { /* silencioso */ }
    finally { setLoading(false); }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 3_000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (refreshSignal > 0) load();
  }, [refreshSignal]);

  if (loading) return <p className="text-sm text-muted-foreground p-2">Cargando consolas…</p>;

  if (workers.length === 0) {
    return (
      <div className="p-3 text-xs text-muted-foreground italic">
        Sin workers aún. Cuando el orquestador lance un sub-agente o Claude Code, aparecerá acá.
      </div>
    );
  }

  return (
    <div className="p-2 space-y-2">
      {workers.map((w) => (
        <WorkerCard key={w.id} worker={w} />
      ))}
    </div>
  );
}
