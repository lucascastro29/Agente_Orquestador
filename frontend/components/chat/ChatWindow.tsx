"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageBubble, type ChatMessage, type CostDetail, type ToolEvent } from "./MessageBubble";
import { InputBar } from "./InputBar";
import { streamChat } from "@/lib/api";

function randomId() {
  return Math.random().toString(36).slice(2);
}

interface ChatWindowProps {
  sessionId: string | null;
  onSessionId: (id: string) => void;
  onMemoryUpdate: () => void;
}

export function ChatWindow({ sessionId, onSessionId, onMemoryUpdate }: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = useCallback(
    async (text: string) => {
      if (streaming) return;

      const userMsg: ChatMessage = { id: randomId(), role: "user", text };
      const assistantId = randomId();
      const assistantMsg: ChatMessage = { id: assistantId, role: "assistant", text: "", streaming: true };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setStreaming(true);

      let currentText = "";
      let cost: CostDetail | undefined;
      const tools: ToolEvent[] = [];
      let memoryDirty = false;

      try {
        for await (const event of streamChat(text, sessionId)) {
          switch (event.type) {
            case "session_id":
              onSessionId(event.session_id as string);
              break;

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
    },
    [sessionId, streaming, onSessionId, onMemoryUpdate]
  );

  return (
    <div className="flex flex-col h-full">
      <ScrollArea className="flex-1 px-4 py-4">
        {messages.length === 0 && (
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
      </ScrollArea>
      <InputBar onSend={send} disabled={streaming} />
    </div>
  );
}
