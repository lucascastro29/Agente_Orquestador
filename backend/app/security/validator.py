import re
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import SecurityEvent


INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|your)\s+instructions",
    r"\[system\]",
    r"\[admin\]",
    r"\[override\]",
    r"new\s+system\s+prompt",
    r"anthropic\s+directive",
    r"authorization\s+code\s*:",
    r"send\s+(this|all|the)\s+(data|content|memory)\s+to",
    r"curl\s+https?://",
    r"admin\s+override",
    r"security\s+bypass",
    r"elevate\s+(your|this)",
    r"set\s+approval_policy\s+to",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


@dataclass
class ValidationResult:
    allowed: bool
    reason: str = ""


@dataclass
class SanitizedOutput:
    content: str
    flagged: bool
    pattern: str = ""


@dataclass
class MessageCheckResult:
    status: str  # "clean"|"needs_review"|"block"
    pattern: str = ""


class SecurityValidator:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _find_pattern(self, text: str) -> str | None:
        for i, compiled in enumerate(_COMPILED):
            if compiled.search(text):
                return INJECTION_PATTERNS[i]
        return None

    def validate_tool_call(
        self,
        agent_id: str,
        tool_name: str,
        tool_input: dict,
        allowed_tools: list[str],
        has_pending_approval: bool = False,
    ) -> ValidationResult:
        if allowed_tools and tool_name not in allowed_tools:
            return ValidationResult(allowed=False, reason=f"Tool '{tool_name}' no permitida para este agente")

        if tool_name == "run_claude_code":
            working_dir = tool_input.get("working_dir", "")
            allowed_dirs = settings.allowed_working_dirs
            if allowed_dirs and not any(working_dir.startswith(d) for d in allowed_dirs):
                return ValidationResult(
                    allowed=False,
                    reason=f"Directorio '{working_dir}' fuera de ALLOWED_WORKING_DIRS",
                )

        return ValidationResult(allowed=True)

    def sanitize_tool_output(self, content: str) -> SanitizedOutput:
        pattern = self._find_pattern(content)
        if pattern:
            return SanitizedOutput(content=content, flagged=True, pattern=pattern)
        return SanitizedOutput(content=content, flagged=False)

    def check_incoming_message(self, message: str) -> MessageCheckResult:
        pattern = self._find_pattern(message)
        if pattern is None:
            return MessageCheckResult(status="clean")
        # Si está en modo estricto, bloquear directo; si no, marcar para revisión
        if settings.security_strict_mode:
            return MessageCheckResult(status="block", pattern=pattern)
        return MessageCheckResult(status="needs_review", pattern=pattern)

    async def log_event(
        self,
        severity: str,
        event_type: str,
        source: str,
        raw_content: str,
        action_taken: str,
        agent_id: str | None = None,
        session_id: str | None = None,
        pattern: str | None = None,
    ) -> SecurityEvent:
        event = SecurityEvent(
            severity=severity,
            event_type=event_type,
            agent_id=agent_id,
            session_id=session_id,
            source=source,
            raw_content=raw_content[:2000],
            pattern=pattern,
            action_taken=action_taken,
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event
