import httpx

from app.config import settings

_BASE = "https://api.telegram.org/bot"


async def send_message(chat_id: str, text: str, parse_mode: str = "HTML") -> None:
    if not settings.telegram_bot_token:
        return
    url = f"{_BASE}{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json=payload)


async def send_with_approval(
    chat_id: str, tool_name: str, tool_input: dict, approval_id: str
) -> None:
    from app.telegram.buttons import build_approval_keyboard

    text = (
        f"⚙️ <b>Acción pendiente de aprobación</b>\n\n"
        f"<b>Tool:</b> <code>{tool_name}</code>\n"
        f"<b>Input:</b>\n<pre>{_format_input(tool_input)}</pre>"
    )
    keyboard = build_approval_keyboard(tool_name, tool_input, approval_id)

    if not settings.telegram_bot_token:
        return
    url = f"{_BASE}{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": keyboard,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json=payload)


async def send_security_alert(chat_id: str, event_type: str, severity: str, fragment: str) -> None:
    icon = "🚨" if severity == "critical" else "⚠️"
    text = (
        f"{icon} <b>Alerta de seguridad</b>\n"
        f"<b>Tipo:</b> {event_type}\n"
        f"<b>Severidad:</b> {severity}\n"
        f"<b>Fragmento:</b> <code>{fragment[:200]}</code>"
    )
    await send_message(chat_id, text)


def _format_input(tool_input: dict) -> str:
    import json
    return json.dumps(tool_input, indent=2, ensure_ascii=False)[:800]
