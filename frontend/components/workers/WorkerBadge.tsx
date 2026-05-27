"use client";

import { useEffect, useState } from "react";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

const ACTIVE_STATUSES = new Set(["pending", "running", "waiting_input"]);

interface WorkerBadgeProps {
  onOpen: () => void;
}

export function WorkerBadge({ onOpen }: WorkerBadgeProps) {
  const [activeCount, setActiveCount] = useState(0);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!TOKEN) return;

    const url = `${BASE}/api/workers/stream?token=${encodeURIComponent(TOKEN)}`;
    const es = new EventSource(url);

    es.addEventListener("workers_update", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setActiveCount(data.active_count ?? 0);
        setConnected(true);
      } catch {
        // malformed event — ignore
      }
    });

    es.onerror = () => setConnected(false);
    es.onopen = () => setConnected(true);

    return () => es.close();
  }, []);

  if (!connected || activeCount === 0) return null;

  return (
    <button
      onClick={onOpen}
      title="Ver consolas de workers"
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-zinc-800 hover:bg-zinc-700 transition-colors text-xs text-zinc-300 border border-zinc-700"
    >
      <span className="relative flex h-2 w-2 shrink-0">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
      </span>
      {activeCount} worker{activeCount !== 1 ? "s" : ""} activo{activeCount !== 1 ? "s" : ""}
    </button>
  );
}
