"use client";

import { useState, useRef, KeyboardEvent } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Send, Loader2 } from "lucide-react";

interface InputBarProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function InputBar({ onSend, disabled }: InputBarProps) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    ref.current?.focus();
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="flex gap-2 items-end p-4 border-t border-border bg-background">
      <Textarea
        ref={ref}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Escribí un mensaje… (Enter para enviar, Shift+Enter para nueva línea)"
        className="min-h-[44px] max-h-40 resize-none"
        disabled={disabled}
        rows={1}
      />
      <Button onClick={submit} disabled={disabled || !value.trim()} size="icon" className="shrink-0">
        {disabled ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
      </Button>
    </div>
  );
}
