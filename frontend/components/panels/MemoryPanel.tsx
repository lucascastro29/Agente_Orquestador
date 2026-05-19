"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { getMemory, type MemoryEntry } from "@/lib/api";

const CATEGORY_COLORS: Record<string, string> = {
  proyecto:       "bg-blue-100 text-blue-800",
  objetivo_actual:"bg-green-100 text-green-800",
  preferencia:    "bg-purple-100 text-purple-800",
  persona:        "bg-orange-100 text-orange-800",
  recordatorio:   "bg-yellow-100 text-yellow-800",
  nota_libre:     "bg-gray-100 text-gray-800",
};

interface MemoryPanelProps {
  refreshSignal: number;
}

export function MemoryPanel({ refreshSignal }: MemoryPanelProps) {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getMemory()
      .then(setEntries)
      .finally(() => setLoading(false));
  }, [refreshSignal]);

  if (loading) return <p className="text-sm text-muted-foreground p-2">Cargando memoria…</p>;
  if (entries.length === 0)
    return <p className="text-sm text-muted-foreground p-2">Sin entradas de memoria todavía.</p>;

  const byCategory: Record<string, MemoryEntry[]> = {};
  for (const e of entries) {
    (byCategory[e.category] ??= []).push(e);
  }

  return (
    <div className="space-y-3 p-2">
      {Object.entries(byCategory).map(([cat, items]) => (
        <div key={cat}>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">{cat}</p>
          <div className="space-y-1">
            {items.map((e) => (
              <div key={e.id} className="flex items-start gap-2 text-sm">
                <Badge className={`shrink-0 text-[10px] ${CATEGORY_COLORS[e.category] ?? ""}`} variant="outline">
                  {e.key}
                </Badge>
                <span className="text-foreground">{e.value.text ?? JSON.stringify(e.value)}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
