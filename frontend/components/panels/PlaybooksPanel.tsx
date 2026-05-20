"use client";

import { useEffect, useState, useCallback } from "react";
import { Play, Trash2, ChevronDown, ChevronUp, Zap, ArrowRight, Loader2 } from "lucide-react";
import { getPlaybooks, deletePlaybook, runPlaybook, type PlaybookEntry } from "@/lib/api";

const TOOL_COLOR: Record<string, string> = {
  read_gmail_inbox:     "bg-red-500/10 text-red-400 border-red-500/30",
  notion_create_task:   "bg-purple-500/10 text-purple-400 border-purple-500/30",
  notion_update_task:   "bg-purple-500/10 text-purple-400 border-purple-500/30",
  notion_search:        "bg-purple-500/10 text-purple-400 border-purple-500/30",
  run_claude_code:      "bg-blue-500/10 text-blue-400 border-blue-500/30",
  create_subagent:      "bg-sky-500/10 text-sky-400 border-sky-500/30",
  read_calendar_events: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  chrome_navigate:      "bg-orange-500/10 text-orange-400 border-orange-500/30",
  schedule_task:        "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
};

function ToolBadge({ tool }: { tool: string }) {
  const color = TOOL_COLOR[tool] ?? "bg-zinc-800 text-zinc-400 border-zinc-700";
  const short = tool.replace(/_/g, " ");
  return (
    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${color} shrink-0`}>
      {short}
    </span>
  );
}

interface Step {
  label: string;
  tool: string;
  params?: Record<string, unknown>;
}

function StepFlow({ steps }: { steps: Step[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {steps.map((step, i) => (
        <div key={i} className="flex items-center gap-1">
          <div className="flex flex-col items-center gap-0.5">
            <span className="text-[9px] text-zinc-600">{step.label}</span>
            <ToolBadge tool={step.tool} />
          </div>
          {i < steps.length - 1 && (
            <ArrowRight className="w-3 h-3 text-zinc-700 shrink-0" />
          )}
        </div>
      ))}
    </div>
  );
}

function PlaybookCard({
  playbook,
  onDelete,
  onRun,
}: {
  playbook: PlaybookEntry;
  onDelete: (id: string) => void;
  onRun: (id: string, name: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [running, setRunning] = useState(false);

  const steps: Step[] = Array.isArray(playbook.steps) ? playbook.steps : [];

  async function handleDelete() {
    if (!confirm(`¿Eliminar el playbook "${playbook.name}"?`)) return;
    setDeleting(true);
    try {
      await deletePlaybook(playbook.id);
      onDelete(playbook.id);
    } finally {
      setDeleting(false);
    }
  }

  async function handleRun() {
    setRunning(true);
    try {
      await onRun(playbook.id, playbook.name);
    } finally {
      setRunning(false);
    }
  }

  const lastRun = playbook.last_run_at
    ? new Date(playbook.last_run_at).toLocaleDateString("es-AR", {
        day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
      })
    : null;

  return (
    <div className="border border-zinc-800 rounded-lg bg-zinc-900/40 overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 flex items-start gap-2">
        <Zap className="w-3.5 h-3.5 text-yellow-400 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-1">
            <span className="text-xs font-semibold text-zinc-200 truncate">{playbook.name}</span>
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={handleRun}
                disabled={running}
                className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20 transition-colors disabled:opacity-50"
                title="Ejecutar playbook"
              >
                {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                Run
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="text-zinc-600 hover:text-red-400 transition-colors p-0.5 disabled:opacity-50"
                title="Eliminar"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          </div>

          {playbook.description && (
            <p className="text-[10px] text-zinc-500 mt-0.5 line-clamp-2">{playbook.description}</p>
          )}

          <div className="flex items-center gap-2 mt-1 text-[10px] text-zinc-600">
            <span>{steps.length} paso{steps.length !== 1 ? "s" : ""}</span>
            {playbook.run_count > 0 && <span>{playbook.run_count} ejecuciones</span>}
            {lastRun && <span>último: {lastRun}</span>}
          </div>
        </div>
      </div>

      {/* Flow preview */}
      {steps.length > 0 && (
        <div className="px-3 pb-2">
          {!expanded ? (
            <div className="flex items-center gap-1 flex-wrap">
              {steps.slice(0, 3).map((s, i) => (
                <div key={i} className="flex items-center gap-1">
                  <ToolBadge tool={s.tool} />
                  {i < Math.min(steps.length, 3) - 1 && <ArrowRight className="w-2.5 h-2.5 text-zinc-700" />}
                </div>
              ))}
              {steps.length > 3 && (
                <span className="text-[10px] text-zinc-600">+{steps.length - 3} más</span>
              )}
            </div>
          ) : (
            <div className="space-y-1.5">
              {steps.map((step, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="text-[10px] text-zinc-600 w-4 shrink-0 pt-0.5">{i + 1}.</span>
                  <div className="flex flex-col gap-0.5 min-w-0">
                    <ToolBadge tool={step.tool} />
                    <span className="text-[10px] text-zinc-500">{step.label}</span>
                    {step.params && Object.keys(step.params).length > 0 && (
                      <span className="text-[9px] text-zinc-700 font-mono truncate">
                        {JSON.stringify(step.params)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {steps.length > 0 && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="flex items-center gap-0.5 text-[10px] text-zinc-600 hover:text-zinc-400 mt-1.5 transition-colors"
            >
              {expanded ? <><ChevronUp className="w-3 h-3" /> ocultar pasos</> : <><ChevronDown className="w-3 h-3" /> ver pasos</>}
            </button>
          )}
        </div>
      )}

      {/* Tags */}
      {playbook.tags && playbook.tags.length > 0 && (
        <div className="px-3 pb-2 flex flex-wrap gap-1">
          {playbook.tags.map((tag) => (
            <span key={tag} className="text-[9px] px-1.5 py-0.5 rounded-full bg-zinc-800 text-zinc-500 border border-zinc-700">
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

interface PlaybooksPanelProps {
  onRunPlaybook?: (message: string) => void;
}

export function PlaybooksPanel({ onRunPlaybook }: PlaybooksPanelProps) {
  const [playbooks, setPlaybooks] = useState<PlaybookEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await getPlaybooks();
      setPlaybooks(data);
    } catch { /* silencioso */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, [load]);

  const handleDelete = useCallback((id: string) => {
    setPlaybooks((prev) => prev.filter((p) => p.id !== id));
  }, []);

  const handleRun = useCallback(async (id: string, name: string) => {
    try {
      const result = await runPlaybook(id);
      if (onRunPlaybook && result.prompt) {
        onRunPlaybook(result.prompt);
      }
    } catch { /* silencioso */ }
  }, [onRunPlaybook]);

  if (loading) return <p className="text-xs text-zinc-600 p-3">Cargando playbooks…</p>;

  return (
    <div className="p-2.5 space-y-2">
      {playbooks.length === 0 ? (
        <div className="text-center py-6 space-y-2">
          <Zap className="w-6 h-6 text-zinc-700 mx-auto" />
          <p className="text-xs text-zinc-600 italic">
            Sin playbooks guardados aún.
          </p>
          <p className="text-[10px] text-zinc-700 px-4 text-center">
            Pedile al orquestador que guarde un flujo: "guardá este flujo como playbook"
          </p>
        </div>
      ) : (
        playbooks.map((p) => (
          <PlaybookCard
            key={p.id}
            playbook={p}
            onDelete={handleDelete}
            onRun={handleRun}
          />
        ))
      )}
    </div>
  );
}
