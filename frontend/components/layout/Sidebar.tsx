"use client";

import { useEffect, useState } from "react";
import { getSessions, type SessionEntry } from "@/lib/api";
import { cn } from "@/lib/utils";
import { MessageSquare, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

interface SidebarProps {
  activeSessionId: string | null;
  onSelect: (id: string | null) => void;
}

export function Sidebar({ activeSessionId, onSelect }: SidebarProps) {
  const [sessions, setSessions] = useState<SessionEntry[]>([]);

  useEffect(() => {
    getSessions().then(setSessions);
  }, [activeSessionId]);

  return (
    <div className="w-56 shrink-0 border-r border-border flex flex-col bg-muted/30">
      <div className="p-3 border-b border-border">
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start gap-2"
          onClick={() => onSelect(null)}
        >
          <Plus className="w-3.5 h-3.5" />
          Nueva sesión
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => onSelect(s.id)}
              className={cn(
                "w-full text-left px-3 py-2 rounded-lg text-sm transition-colors hover:bg-muted flex items-start gap-2",
                s.id === activeSessionId && "bg-muted font-medium"
              )}
            >
              <MessageSquare className="w-3.5 h-3.5 mt-0.5 shrink-0 text-muted-foreground" />
              <div className="min-w-0">
                <p className="truncate">{s.title ?? "Sesión"}</p>
                <p className="text-[10px] text-muted-foreground">${s.total_cost_usd.toFixed(4)}</p>
              </div>
            </button>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
