"use client";

import { useState, useCallback } from "react";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { Sidebar } from "@/components/layout/Sidebar";
import { RightPanel } from "@/components/layout/RightPanel";

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [memoryRefresh, setMemoryRefresh] = useState(0);

  const handleMemoryUpdate = useCallback(() => {
    setMemoryRefresh((n) => n + 1);
  }, []);

  const handleSelectSession = useCallback((id: string | null) => {
    setSessionId(id);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <Sidebar activeSessionId={sessionId} onSelect={handleSelectSession} />
      <main className="flex-1 flex flex-col min-w-0">
        <header className="shrink-0 px-4 py-2 border-b border-border flex items-center gap-2">
          <span className="font-semibold text-sm">Agente Orquestador</span>
          {sessionId && (
            <span className="text-xs text-muted-foreground font-mono">{sessionId.slice(0, 8)}…</span>
          )}
        </header>
        <div className="flex-1 min-h-0">
          <ChatWindow
            sessionId={sessionId}
            onSessionId={setSessionId}
            onMemoryUpdate={handleMemoryUpdate}
          />
        </div>
      </main>
      <RightPanel memoryRefresh={memoryRefresh} />
    </div>
  );
}
