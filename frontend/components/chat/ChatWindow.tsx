"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { Volume2, VolumeX } from "lucide-react";
import { MessageBubble, type ChatMessage, type CostDetail, type ToolEvent } from "./MessageBubble";
import { InputBar } from "./InputBar";
import { streamChat, getMessages, synthesizeTTS, type MessageEntry } from "@/lib/api";
import { cn } from "@/lib/utils";

function randomId() {
  return Math.random().toString(36).slice(2);
}

function extractText(content: unknown[]): string {
  return (content ?? [])
    .filter((b): b is { type: string; text?: string } => typeof b === "object" && b !== null)
    .filter((b) => b.type === "text" && typeof b.text === "string")
    .map((b) => b.text as string)
    .join("");
}

function entryToMessage(e: MessageEntry): ChatMessage {
  return {
    id: e.id,
    role: e.role as "user" | "assistant",
    text: extractText(e.content),
    cost: e.cost_usd != null ? {
      turn_cost_usd: e.cost_usd,
      session_cost_usd: 0,
      input_tokens: e.input_tokens ?? 0,
      output_tokens: e.output_tokens ?? 0,
      cache_read_tokens: 0,
      cache_write_tokens: 0,
    } : undefined,
  };
}

const WORKER_TOOLS = new Set(["create_subagent", "run_claude_code", "cancel_worker", "get_workers_status"]);

interface ChatWindowProps {
  sessionId: string | null;
  onSessionId: (id: string) => void;
  onMemoryUpdate: () => void;
  onAgentsUpdate: () => void;
  externalPrompt?: string | null;
  onExternalPromptConsumed?: () => void;
}

export function ChatWindow({ sessionId, onSessionId, onMemoryUpdate, onAgentsUpdate, externalPrompt, onExternalPromptConsumed }: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [loading, setLoading] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState<boolean>(false);

  useEffect(() => {
    setTtsEnabled(localStorage.getItem("tts_enabled") === "true");
  }, []);

  const toggleTts = useCallback(() => {
    setTtsEnabled((prev) => {
      const next = !prev;
      localStorage.setItem("tts_enabled", String(next));
      return next;
    });
  }, []);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const loadedSessionRef = useRef<string | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  // true = el usuario está en el fondo (o no scrolleó manualmente)
  const stickToBottomRef = useRef(true);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickToBottomRef.current = distFromBottom < 80;
  }, []);

  // Cargar historial cuando cambia la sesión
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      loadedSessionRef.current = null;
      return;
    }
    if (loadedSessionRef.current === sessionId) return;
    loadedSessionRef.current = sessionId;
    setMessages([]);
    stickToBottomRef.current = true;
    setLoading(true);
    getMessages(sessionId)
      .then((entries) => setMessages(entries.map(entryToMessage)))
      .catch(() => setMessages([]))
      .finally(() => setLoading(false));
  }, [sessionId]);

  // Auto-scroll solo si el usuario está en el fondo
  useEffect(() => {
    if (stickToBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  const send = useCallback(
    async (text: string) => {
      if (streaming) return;
      // Desbloquear AudioContext dentro del gesto del usuario (click en Enviar)
      if (!audioCtxRef.current) {
        audioCtxRef.current = new AudioContext();
      }
      audioCtxRef.current.resume();
      // Al enviar, siempre volver al fondo
      stickToBottomRef.current = true;

      const userMsg: ChatMessage = { id: randomId(), role: "user", text };
      const assistantId = randomId();
      const assistantMsg: ChatMessage = { id: assistantId, role: "assistant", text: "", streaming: true };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setStreaming(true);

      let currentText = "";
      let cost: CostDetail | undefined;
      const tools: ToolEvent[] = [];
      let memoryDirty = false;
      let agentsDirty = false;

      try {
        for await (const event of streamChat(text, sessionId)) {
          switch (event.type) {
            case "session_id": {
              const newId = event.session_id as string;
              // Marcar como ya cargada ANTES de que onSessionId dispare el useEffect,
              // para que no borre los mensajes en curso ni haga fetch vacío al DB.
              loadedSessionRef.current = newId;
              onSessionId(newId);
              break;
            }

            case "text_delta":
              currentText += event.text as string;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, text: currentText } : m
                )
              );
              break;

            case "tool_use_start":
              tools.push({ tool_name: event.tool_name as string, tool_input: event.tool_input as Record<string, unknown> });
              break;

            case "tool_use_result": {
              const last = tools[tools.length - 1];
              if (last && last.tool_name === event.tool_name) {
                last.output = event.output;
              }
              if (WORKER_TOOLS.has(event.tool_name as string)) {
                agentsDirty = true;
                onAgentsUpdate(); // refresh inmediato, sin esperar fin del stream
              }
              break;
            }

            case "memory_updated":
              memoryDirty = true;
              break;

            case "cost_update":
              cost = event.tokens as CostDetail;
              if (cost) {
                cost.turn_cost_usd = event.turn_cost as number;
                cost.session_cost_usd = event.session_cost as number;
              }
              break;

            case "security_alert":
              currentText = "⚠️ Mensaje bloqueado por política de seguridad.";
              break;

            case "done":
              break;
          }
        }
      } catch (err) {
        currentText += "\n\n⚠️ Error de conexión con el servidor.";
      }

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, text: currentText, streaming: false, cost, tools: tools.length ? tools : undefined }
            : m
        )
      );
      setStreaming(false);

      if (memoryDirty) onMemoryUpdate();
      if (agentsDirty) {
        onAgentsUpdate();
        // Polling: esperar el resultado del sub-agente y mostrarlo en el chat.
        // Tomamos un snapshot de DB *ahora* para usar sus UUIDs reales como baseline,
        // evitando que el poll agregue duplicados del turno actual (que en cliente
        // tiene IDs aleatorios pero en DB tiene UUIDs distintos).
        const currentSessionId = loadedSessionRef.current;
        if (currentSessionId) {
          let attempts = 0;
          getMessages(currentSessionId).then((baseline) => {
            const baselineIds = new Set(baseline.map((m) => m.id));
            const poll = setInterval(async () => {
              attempts++;
              if (attempts > 60) { clearInterval(poll); return; }
              try {
                const fresh = await getMessages(currentSessionId);
                const newMsgs = fresh.filter(
                  (m) => !baselineIds.has(m.id) && m.role === "assistant"
                );
                if (newMsgs.length > 0) {
                  clearInterval(poll);
                  onAgentsUpdate();
                  // Deduplicar contra el estado actual (por si hubo race condition)
                  setMessages((prev) => {
                    const prevIds = new Set(prev.map((m) => m.id));
                    const toAdd = newMsgs.filter((m) => !prevIds.has(m.id));
                    return toAdd.length > 0 ? [...prev, ...toAdd.map(entryToMessage)] : prev;
                  });
                }
              } catch { /* silencioso */ }
            }, 3_000);
          });
        }
      }

      // TTS: sintetizar y reproducir via AudioContext (evita bloqueo de autoplay)
      if (ttsEnabled && currentText && audioCtxRef.current) {
        const ctx = audioCtxRef.current;
        synthesizeTTS(currentText).then(async (url) => {
          if (!url) return;
          try {
            const resp = await fetch(url);
            const buf = await resp.arrayBuffer();
            URL.revokeObjectURL(url);
            const decoded = await ctx.decodeAudioData(buf);
            const src = ctx.createBufferSource();
            src.buffer = decoded;
            src.connect(ctx.destination);
            src.start();
          } catch {
            URL.revokeObjectURL(url);
          }
        });
      }
    },
    [sessionId, streaming, onSessionId, onMemoryUpdate, onAgentsUpdate, ttsEnabled]
  );

  useEffect(() => {
    if (externalPrompt) {
      send(externalPrompt);
      onExternalPromptConsumed?.();
    }
  }, [externalPrompt]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Barra superior con toggle TTS */}
      <div className="flex justify-end px-4 pt-2 pb-0">
        <button
          onClick={toggleTts}
          title={ttsEnabled ? "Desactivar narración en audio" : "Activar narración en audio"}
          className={cn(
            "flex items-center gap-1 px-2 py-1 rounded-lg text-xs transition-colors",
            ttsEnabled
              ? "bg-primary/10 text-primary hover:bg-primary/20"
              : "text-muted-foreground hover:text-foreground hover:bg-muted"
          )}
        >
          {ttsEnabled ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
          <span>{ttsEnabled ? "TTS ON" : "TTS"}</span>
        </button>
      </div>
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 py-4 min-h-0"
      >
        {loading && (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm mt-20">
            Cargando conversación…
          </div>
        )}
        {!loading && messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-muted-foreground text-sm mt-20">
            Escribí algo para empezar a chatear con el orquestador.
          </div>
        )}
        <div className="space-y-4 max-w-3xl mx-auto">
          {messages.map((m) => (
            <MessageBubble key={m.id} msg={m} />
          ))}
        </div>
        <div ref={bottomRef} />
      </div>
      <InputBar onSend={send} disabled={streaming} />
    </div>
  );
}
