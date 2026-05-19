#!/usr/bin/env python3
"""Hook de Claude Code para el evento Stop. Notifica al backend."""
import json
import os
import sys

import httpx

backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
token = os.environ.get("APP_AUTH_TOKEN", "")

try:
    event = json.loads(sys.stdin.read())
except Exception:
    event = {}

try:
    httpx.post(
        f"{backend_url}/api/workers/hook",
        json={"event_type": "Stop", "payload": event},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
except Exception as exc:
    print(f"[notify_stop] Error: {exc}", file=sys.stderr)
