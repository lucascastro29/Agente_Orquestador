"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getSecurityEvents, resolveSecurityEvent, type SecurityEventEntry } from "@/lib/api";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-800 border-red-200",
  warning:  "bg-yellow-100 text-yellow-800 border-yellow-200",
  info:     "bg-blue-100 text-blue-800 border-blue-200",
};

export function SecurityPanel() {
  const [events, setEvents] = useState<SecurityEventEntry[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    getSecurityEvents()
      .then(setEvents)
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  async function resolve(id: string) {
    await resolveSecurityEvent(id);
    setEvents((prev) => prev.map((e) => (e.id === id ? { ...e, resolved: true } : e)));
  }

  const unresolved = events.filter((e) => !e.resolved);
  const resolved   = events.filter((e) => e.resolved);

  if (loading) return <p className="text-sm text-muted-foreground p-2">Cargando eventos…</p>;
  if (events.length === 0) return <p className="text-sm text-muted-foreground p-2">Sin eventos de seguridad.</p>;

  function EventRow({ e }: { e: SecurityEventEntry }) {
    return (
      <div className={`text-xs border rounded p-2 space-y-1 ${SEVERITY_COLORS[e.severity] ?? ""}`}>
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold">{e.event_type}</span>
          <Badge variant="outline" className="text-[10px]">{e.severity}</Badge>
        </div>
        <p className="text-muted-foreground line-clamp-2">{e.raw_content}</p>
        {e.pattern && <p className="font-mono opacity-70">pattern: {e.pattern}</p>}
        {!e.resolved && (
          <Button size="sm" variant="ghost" className="h-6 text-xs px-2" onClick={() => resolve(e.id)}>
            Marcar resuelto
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2 p-2">
      {unresolved.length > 0 && (
        <>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Sin resolver ({unresolved.length})</p>
          {unresolved.map((e) => <EventRow key={e.id} e={e} />)}
        </>
      )}
      {resolved.length > 0 && (
        <>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mt-3">Resueltos</p>
          {resolved.map((e) => <EventRow key={e.id} e={e} />)}
        </>
      )}
    </div>
  );
}
