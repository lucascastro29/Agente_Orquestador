"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

export interface CostDetail {
  turn_cost_usd: number;
  session_cost_usd: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
}

export interface ToolEvent {
  tool_name: string;
  tool_input?: Record<string, unknown>;
  output?: unknown;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
  cost?: CostDetail;
  tools?: ToolEvent[];
}

function CostFooter({ cost }: { cost: CostDetail }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 text-xs text-muted-foreground">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 hover:text-foreground transition-colors"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        💰 ${cost.turn_cost_usd.toFixed(5)} este turno · ${cost.session_cost_usd.toFixed(4)} sesión
      </button>
      {open && (
        <div className="mt-1 pl-4 grid grid-cols-2 gap-x-4 gap-y-0.5">
          <span>Input tokens:</span><span>{cost.input_tokens}</span>
          <span>Output tokens:</span><span>{cost.output_tokens}</span>
          <span>Cache read:</span><span>{cost.cache_read_tokens}</span>
          <span>Cache write:</span><span>{cost.cache_write_tokens}</span>
        </div>
      )}
    </div>
  );
}

function ToolTrace({ tools }: { tools: ToolEvent[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 text-xs border border-border rounded p-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-muted-foreground hover:text-foreground"
      >
        {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        🔧 {tools.length} tool{tools.length !== 1 ? "s" : ""} ejecutada{tools.length !== 1 ? "s" : ""}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {tools.map((t, i) => (
            <div key={i} className="pl-3 border-l-2 border-muted">
              <div className="font-mono font-semibold">{t.tool_name}</div>
              {t.tool_input && (
                <pre className="text-[10px] text-muted-foreground whitespace-pre-wrap">
                  {JSON.stringify(t.tool_input, null, 2).slice(0, 300)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-3 text-sm",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-sm"
            : "bg-muted text-foreground rounded-bl-sm"
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{msg.text}</p>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.text}</ReactMarkdown>
            {msg.streaming && (
              <span className="inline-block w-1.5 h-4 bg-current animate-pulse ml-0.5 align-text-bottom" />
            )}
          </div>
        )}

        {!isUser && msg.tools && msg.tools.length > 0 && <ToolTrace tools={msg.tools} />}
        {!isUser && msg.cost && <CostFooter cost={msg.cost} />}
      </div>
    </div>
  );
}
