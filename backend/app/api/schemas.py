from datetime import datetime
from typing import Any
from pydantic import BaseModel


class TTSSynthesizeRequest(BaseModel):
    text: str


class ChatRequest(BaseModel):
    agent_id: str = "orchestrator"
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    text: str
    blocked: bool = False
    blocked_reason: str = ""
    pending_approval_id: str | None = None
    cost: dict = {}


class SessionOut(BaseModel):
    id: str
    agent_id: str
    title: str | None
    channel: str
    total_cost_usd: float
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: str
    session_id: str
    position: int
    role: str
    content: list[Any]
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    created_at: datetime


class MemoryIn(BaseModel):
    key: str
    value: str
    category: str


class MemoryOut(BaseModel):
    id: str
    key: str
    value: dict
    category: str
    created_at: datetime
    updated_at: datetime


class ApprovalAction(BaseModel):
    action: str           # "approve"|"reject"
    edited_input: dict | None = None


class ApprovalOut(BaseModel):
    id: str
    session_id: str
    tool_name: str
    tool_input: dict
    status: str
    created_at: datetime


class SecurityEventOut(BaseModel):
    id: str
    severity: str
    event_type: str
    source: str
    raw_content: str
    pattern: str | None
    action_taken: str
    resolved: bool
    created_at: datetime


class WorkerOut(BaseModel):
    id: str
    parent_id: str | None
    agent_id: str
    session_id: str
    type: str
    status: str
    prompt: str
    working_dir: str | None
    result_summary: str | None
    cost_usd: float
    notion_task_id: str | None
    error: str | None
    notified: bool
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TranscribeResponse(BaseModel):
    text: str


class AgentOut(BaseModel):
    id: str
    type: str            # "orchestrator" | "subagent"
    model: str
    tools: list[str]
    max_workers: int | None
    approval_policy: str
    active_workers: int
    total_sessions: int


class ScheduleTaskOut(BaseModel):
    name: str
    label: str
    schedule: str
    enabled: bool
    last_checked_at: datetime | None


class ScheduledTaskOut(BaseModel):
    id: str
    name: str
    description: str | None
    cron_expr: str
    enabled: bool
    action_type: str
    action_config: dict
    next_run_at: datetime | None
    last_run_at: datetime | None
    run_count: int
    last_error: str | None
    created_at: datetime
