from datetime import datetime
from typing import Any
from pydantic import BaseModel


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
