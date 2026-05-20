const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN = process.env.NEXT_PUBLIC_API_TOKEN ?? "";

function headers(extra: Record<string, string> = {}): Record<string, string> {
  return { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json", ...extra };
}

export interface SSEEvent {
  type:
    | "session_id"
    | "text_delta"
    | "tool_use_start"
    | "tool_use_result"
    | "memory_updated"
    | "cost_update"
    | "approval_needed"
    | "security_alert"
    | "done";
  [key: string]: unknown;
}

export interface MemoryEntry {
  id: string;
  key: string;
  value: { text?: string; [k: string]: unknown };
  category: string;
  created_at: string;
  updated_at: string;
}

export interface SessionEntry {
  id: string;
  agent_id: string;
  title: string | null;
  channel: string;
  total_cost_usd: number;
  created_at: string;
  updated_at: string;
}

export interface MessageEntry {
  id: string;
  position: number;
  role: string;
  content: unknown[];
  model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  created_at: string;
}

export interface SecurityEventEntry {
  id: string;
  severity: string;
  event_type: string;
  source: string;
  raw_content: string;
  pattern: string | null;
  action_taken: string;
  resolved: boolean;
  created_at: string;
}

export async function* streamChat(
  message: string,
  sessionId: string | null
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${BASE}/api/chat/stream`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          yield JSON.parse(line.slice(6)) as SSEEvent;
        } catch {
          // ignorar líneas malformadas
        }
      }
    }
  }
}

export async function getMemory(): Promise<MemoryEntry[]> {
  const res = await fetch(`${BASE}/api/memory`, { headers: headers() });
  return res.json();
}

export async function getSessions(): Promise<SessionEntry[]> {
  const res = await fetch(`${BASE}/api/sessions`, { headers: headers() });
  return res.json();
}

export async function deleteSession(id: string): Promise<void> {
  await fetch(`${BASE}/api/sessions/${id}`, {
    method: "DELETE",
    headers: headers(),
  });
}

export async function getMessages(sessionId: string): Promise<MessageEntry[]> {
  const res = await fetch(`${BASE}/api/sessions/${sessionId}/messages`, {
    headers: headers(),
  });
  return res.json();
}

export async function getSecurityEvents(): Promise<SecurityEventEntry[]> {
  const res = await fetch(`${BASE}/api/security/events`, { headers: headers() });
  return res.json();
}

export async function resolveSecurityEvent(id: string): Promise<void> {
  await fetch(`${BASE}/api/security/events/${id}/resolve`, {
    method: "POST",
    headers: headers(),
  });
}

export interface AgentEntry {
  id: string;
  type: string;
  model: string;
  tools: string[];
  max_workers: number | null;
  approval_policy: string;
  active_workers: number;
  total_sessions: number;
  total_runs: number;
}

export interface ScheduleTaskEntry {
  name: string;
  label: string;
  schedule: string;
  enabled: boolean;
  last_checked_at: string | null;
}

export async function transcribeAudio(blob: Blob): Promise<string> {
  const form = new FormData();
  form.append("file", blob, "voice.webm");
  const res = await fetch(`${BASE}/api/transcribe`, {
    method: "POST",
    headers: { Authorization: `Bearer ${TOKEN}` },
    body: form,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  return (data.text ?? "").trim();
}

export async function getAgents(): Promise<AgentEntry[]> {
  const res = await fetch(`${BASE}/api/agents`, { headers: headers() });
  return res.json();
}

export async function getSchedule(): Promise<ScheduleTaskEntry[]> {
  const res = await fetch(`${BASE}/api/schedule`, { headers: headers() });
  return res.json();
}

export interface UserScheduledTask {
  id: string;
  name: string;
  description: string | null;
  cron_expr: string;
  enabled: boolean;
  action_type: string;
  next_run_at: string | null;
  last_run_at: string | null;
  run_count: number;
  last_error: string | null;
  created_at: string;
}

export async function getScheduledTasks(): Promise<UserScheduledTask[]> {
  const res = await fetch(`${BASE}/api/scheduled-tasks`, { headers: headers() });
  return res.json();
}

export async function toggleScheduledTask(id: string, enabled: boolean): Promise<void> {
  await fetch(`${BASE}/api/scheduled-tasks/${id}/toggle`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify({ enabled }),
  });
}

export async function deleteScheduledTask(id: string): Promise<void> {
  await fetch(`${BASE}/api/scheduled-tasks/${id}`, {
    method: "DELETE",
    headers: headers(),
  });
}

export interface PlaybookEntry {
  id: string;
  name: string;
  description: string | null;
  steps: Array<{ label: string; tool: string; params?: Record<string, unknown> }>;
  tags: string[];
  run_count: number;
  last_run_at: string | null;
  created_at: string;
}

export async function getPlaybooks(): Promise<PlaybookEntry[]> {
  const res = await fetch(`${BASE}/api/playbooks`, { headers: headers() });
  return res.json();
}

export async function deletePlaybook(id: string): Promise<void> {
  await fetch(`${BASE}/api/playbooks/${id}`, {
    method: "DELETE",
    headers: headers(),
  });
}

export async function runPlaybook(id: string): Promise<{ prompt: string }> {
  const res = await fetch(`${BASE}/api/playbooks/${id}/run`, {
    method: "POST",
    headers: headers(),
  });
  return res.json();
}

export async function synthesizeTTS(text: string): Promise<string | null> {
  try {
    const res = await fetch(`${BASE}/api/tts/synthesize`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ text }),
    });
    if (!res.ok) return null;
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  } catch {
    return null;
  }
}
