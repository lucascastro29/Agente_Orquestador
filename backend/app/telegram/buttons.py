def build_approval_keyboard(tool_name: str, tool_input: dict, approval_id: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✓ Confirmar", "callback_data": f"approve:{approval_id}"},
                {"text": "✗ Cancelar",  "callback_data": f"reject:{approval_id}"},
            ]
        ]
    }
