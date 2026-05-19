"use client";

import { useState, useRef, KeyboardEvent, useCallback } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Send, Loader2, Mic, MicOff } from "lucide-react";
import { transcribeAudio } from "@/lib/api";

interface InputBarProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function InputBar({ onSend, disabled }: InputBarProps) {
  const [value, setValue] = useState("");
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

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

  const startRecording = useCallback(async () => {
    if (recording || transcribing) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      const mr = new MediaRecorder(stream);
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.start();
      mediaRef.current = mr;
      setRecording(true);
    } catch {
      alert("No se pudo acceder al micrófono.");
    }
  }, [recording, transcribing]);

  const stopRecording = useCallback(async () => {
    const mr = mediaRef.current;
    if (!mr || !recording) return;
    setRecording(false);
    setTranscribing(true);

    await new Promise<void>((resolve) => {
      mr.onstop = () => resolve();
      mr.stop();
      mr.stream.getTracks().forEach((t) => t.stop());
    });

    try {
      const blob = new Blob(chunksRef.current, { type: "audio/webm" });
      if (blob.size < 1000) { setTranscribing(false); return; }
      const text = await transcribeAudio(blob);
      if (text) setValue((prev) => prev ? `${prev} ${text}` : text);
    } catch {
      // silencioso — el backend ya logea el error
    } finally {
      setTranscribing(false);
      ref.current?.focus();
    }
  }, [recording]);

  const isBusy = disabled || transcribing;

  return (
    <div className="flex gap-2 items-end p-4 border-t border-border bg-background">
      <Textarea
        ref={ref}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Escribí un mensaje… (Enter para enviar, Shift+Enter para nueva línea)"
        className="min-h-[44px] max-h-40 resize-none"
        disabled={isBusy}
        rows={1}
      />

      {/* Botón micrófono — mantener presionado para grabar */}
      <Button
        size="icon"
        variant={recording ? "destructive" : "outline"}
        className="shrink-0"
        disabled={isBusy && !recording}
        onMouseDown={startRecording}
        onMouseUp={stopRecording}
        onMouseLeave={recording ? stopRecording : undefined}
        onTouchStart={(e) => { e.preventDefault(); startRecording(); }}
        onTouchEnd={(e) => { e.preventDefault(); stopRecording(); }}
        title="Mantener presionado para grabar"
      >
        {transcribing
          ? <Loader2 className="w-4 h-4 animate-spin" />
          : recording
            ? <MicOff className="w-4 h-4" />
            : <Mic className="w-4 h-4" />}
      </Button>

      <Button onClick={submit} disabled={isBusy || !value.trim()} size="icon" className="shrink-0">
        {isBusy && !recording ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
      </Button>
    </div>
  );
}
