#!/usr/bin/env python3
"""Configura los hooks de Claude Code en ~/.claude/settings.json.
Ejecutar una sola vez: python scripts/setup_hooks.py
"""
import json
import os
import pathlib
import sys

REPO_DIR = pathlib.Path(__file__).parent.parent.resolve()
SETTINGS_PATH = pathlib.Path.home() / ".claude" / "settings.json"
NOTIFY_STOP = str(REPO_DIR / "scripts" / "notify_stop.py")
NOTIFY_NOTIF = str(REPO_DIR / "scripts" / "notify_notification.py")

HOOKS_TO_ADD = {
    "Stop": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"python {NOTIFY_STOP}",
                }
            ],
        }
    ],
    "Notification": [
        {
            "matcher": "",
            "hooks": [
                {
                    "type": "command",
                    "command": f"python {NOTIFY_NOTIF}",
                }
            ],
        }
    ],
}


def main() -> None:
    # Leer settings existentes
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError:
                settings = {}
    else:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        settings = {}

    existing_hooks = settings.get("hooks", {})

    # Agregar hooks sin pisar los existentes
    for event_name, hook_list in HOOKS_TO_ADD.items():
        if event_name not in existing_hooks:
            existing_hooks[event_name] = hook_list
            print(f"✓ Hook '{event_name}' agregado.")
        else:
            # Verificar si ya está nuestro hook
            existing_cmds = [
                h.get("command", "")
                for entry in existing_hooks[event_name]
                for h in entry.get("hooks", [])
            ]
            our_cmd = hook_list[0]["hooks"][0]["command"]
            if our_cmd not in existing_cmds:
                existing_hooks[event_name].extend(hook_list)
                print(f"✓ Hook '{event_name}' agregado (junto a hooks existentes).")
            else:
                print(f"— Hook '{event_name}' ya estaba configurado.")

    settings["hooks"] = existing_hooks

    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    print(f"\nSettings guardados en: {SETTINGS_PATH}")
    print("\nAsegurate de tener estas variables de entorno al correr Claude Code:")
    print("  BACKEND_URL=http://localhost:8000")
    print("  APP_AUTH_TOKEN=<tu token>")
    print("\nO agregarlas en tu ~/.zshrc / ~/.bashrc:")
    print("  export BACKEND_URL=http://localhost:8000")
    print("  export APP_AUTH_TOKEN=<tu token>")


if __name__ == "__main__":
    main()
