#!/usr/bin/env python3
"""Hook de Claude Code para el evento Notification.
Reenvía la notificación al backend para que llegue por Telegram.
"""
import json
import os
import sys

backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
token = os.environ.get("APP_AUTH_TOKEN", "")

try:
    event = json.loads(sys.stdin.read())
except Exception:
    event = {}

try:
    import httpx
    httpx.post(
        f"{backend_url}/api/workers/hook",
        json={"event_type": "Notification", "payload": event},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
except Exception as exc:
    print(f"[notify_notification] Error: {exc}", file=sys.stderr)
