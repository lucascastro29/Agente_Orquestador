"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";

interface WorkerEntry {
  id: string;
  type: string;
  status: string;
  prompt: string;
  working_dir: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  result_summary: string | null;
  cost_usd: number;
}

const STATUS_COLOR: Record<string, string> = {
  pending:       "bg-yellow-100 text-yellow-800",
  running:       "bg-blue-100  text-blue-800",
  waiting_input: "bg-purple-100 text-purple-800",
  done:          "bg-green-100 text-green-800",
  failed:        "bg-red-100   text-red-800",
  cancelled:     "bg-gray-100  text-gray-600",
};

const STATUS_ICON: Record<string, string> = {
  pending: "⏳", running: "🔄", waiting_input: "⏸️",
  done: "✅", failed: "❌", cancelled: "🚫",
};

export function TeamPanel() {
  const [workers, setWorkers] = useState<WorkerEntry[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const token = process.env.NEXT_PUBLIC_API_TOKEN ?? "";
      const res = await fetch(`${base}/api/workers`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setWorkers(await res.json());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  if (loading) return <p className="text-sm text-muted-foreground p-2">Cargando workers…</p>;
  if (workers.length === 0)
    return <p className="text-sm text-muted-foreground p-2">Sin workers activos todavía.</p>;

  return (
    <div className="space-y-2 p-2">
      {workers.map((w) => (
        <div key={w.id} className="text-xs border border-border rounded p-2 space-y-1">
          <div className="flex items-center justify-between gap-1">
            <span className="font-mono text-[10px] text-muted-foreground">{w.id.slice(0, 8)}</span>
            <Badge className={`text-[10px] ${STATUS_COLOR[w.status] ?? ""}`} variant="outline">
              {STATUS_ICON[w.status]} {w.status}
            </Badge>
          </div>
          <p className="line-clamp-2 text-foreground">{w.prompt}</p>
          {w.working_dir && (
            <p className="font-mono text-muted-foreground truncate">{w.working_dir}</p>
          )}
          {w.error && <p className="text-red-600 line-clamp-1">{w.error}</p>}
          {w.result_summary && w.status === "done" && (
            <p className="text-green-700 line-clamp-2">{w.result_summary}</p>
          )}
          {w.cost_usd > 0 && (
            <p className="text-muted-foreground">${w.cost_usd.toFixed(5)}</p>
          )}
        </div>
      ))}
    </div>
  );
}
