#!/usr/bin/env python3
"""Hook de Claude Code para el evento Stop.
Lee el transcript local, lo adjunta al payload y notifica al backend.
"""
import json
import os
import sys


def _read_transcript(path: str, max_chars: int = 4000) -> str:
    """Lee las últimas líneas del transcript JSONL y extrae texto legible."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return ""

    # Tomar las últimas 40 líneas para no mandar demasiado
    recent = lines[-40:] if len(lines) > 40 else lines
    fragments = []

    for line in recent:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue

        # Formatos posibles del transcript de Claude Code
        role = obj.get("role") or obj.get("type", "")
        content = obj.get("content") or obj.get("message", {}).get("content", [])

        if role not in ("user", "assistant"):
            # Intentar sacar del campo message anidado
            msg = obj.get("message", {})
            role = msg.get("role", "")
            content = msg.get("content", [])

        if not role or not content:
            continue

        prefix = "[U]" if role == "user" else "[A]"
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += block.get("text", "")
                elif isinstance(block, str):
                    text += block

        if text.strip():
            fragments.append(f"{prefix}: {text.strip()[:400]}")

    excerpt = "\n".join(fragments[-12:])  # últimos 12 intercambios
    return excerpt[:max_chars]


backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
token = os.environ.get("APP_AUTH_TOKEN", "")

try:
    event = json.loads(sys.stdin.read())
except Exception:
    event = {}

# Adjuntar extracto del transcript si el path existe
transcript_path = event.get("transcript_path", "")
if transcript_path:
    event["transcript_excerpt"] = _read_transcript(transcript_path)

try:
    import httpx
    httpx.post(
        f"{backend_url}/api/workers/hook",
        json={"event_type": "Stop", "payload": event},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
except Exception as exc:
    print(f"[notify_stop] Error: {exc}", file=sys.stderr)
