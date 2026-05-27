"use client";

import { useState, useCallback, useEffect } from "react";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { Sidebar } from "@/components/layout/Sidebar";
import { RightPanel } from "@/components/layout/RightPanel";
import { ConsolasPanel } from "@/components/panels/ConsolasPanel";
import { WorkerBadge } from "@/components/workers/WorkerBadge";

const SESSION_KEY = "ao_session_id";

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [memoryRefresh, setMemoryRefresh] = useState(0);
  const [agentsRefresh, setAgentsRefresh] = useState(0);
  const [consolasCollapsed, setConsolasCollapsed] = useState(true);
  const [playbookPrompt, setPlaybookPrompt] = useState<string | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem(SESSION_KEY);
    if (saved) setSessionId(saved);
  }, []);

  const handleMemoryUpdate = useCallback(() => {
    setMemoryRefresh((n) => n + 1);
  }, []);

  const handleAgentsUpdate = useCallback(() => {
    setAgentsRefresh((n) => n + 1);
    // Auto-abrir consolas cuando se lanza un worker
    setConsolasCollapsed(false);
  }, []);

  const handleRunPlaybook = useCallback((message: string) => {
    setPlaybookPrompt(message);
  }, []);

  const handleSelectSession = useCallback((id: string | null) => {
    setSessionId(id);
    if (id) localStorage.setItem(SESSION_KEY, id);
    else localStorage.removeItem(SESSION_KEY);
  }, []);

  const handleSessionId = useCallback((id: string) => {
    setSessionId(id);
    localStorage.setItem(SESSION_KEY, id);
  }, []);

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-zinc-950 text-zinc-100">
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <Sidebar activeSessionId={sessionId} onSelect={handleSelectSession} />
        <main className="flex-1 flex flex-col min-w-0 bg-zinc-950">
          <header className="shrink-0 px-4 py-2.5 border-b border-zinc-800 flex items-center gap-2">
            <span className="font-semibold text-sm text-zinc-100">Agente Orquestador</span>
            {sessionId && (
              <span className="text-xs text-zinc-600 font-mono">{sessionId.slice(0, 8)}…</span>
            )}
            <div className="ml-auto">
              <WorkerBadge onOpen={() => setConsolasCollapsed(false)} />
            </div>
          </header>
          <div className="flex-1 min-h-0">
            <ChatWindow
              sessionId={sessionId}
              onSessionId={handleSessionId}
              onMemoryUpdate={handleMemoryUpdate}
              onAgentsUpdate={handleAgentsUpdate}
              externalPrompt={playbookPrompt}
              onExternalPromptConsumed={() => setPlaybookPrompt(null)}
            />
          </div>
        </main>
        <RightPanel memoryRefresh={memoryRefresh} agentsRefresh={agentsRefresh} onRunPlaybook={handleRunPlaybook} />
      </div>
      <ConsolasPanel
        refreshSignal={agentsRefresh}
        collapsed={consolasCollapsed}
        onToggle={() => setConsolasCollapsed((v) => !v)}
      />
    </div>
  );
}
