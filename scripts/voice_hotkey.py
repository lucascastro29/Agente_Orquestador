#!/usr/bin/env python3
"""Hotkey de voz — macOS (Cmd+<) y Windows/Linux (Ctrl+<).

Dependencias (instalar una sola vez):
    pip install pynput sounddevice scipy numpy httpx plyer

Uso:
    python scripts/voice_hotkey.py

Variables de entorno:
    BACKEND_URL=http://localhost:8000
    APP_AUTH_TOKEN=<tu token>
"""
import io
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time

_missing = []
try:
    import numpy as np
except ImportError:
    _missing.append("numpy")
try:
    import sounddevice as sd
except ImportError:
    _missing.append("sounddevice")
try:
    from scipy.io import wavfile
except ImportError:
    _missing.append("scipy")
try:
    import httpx
except ImportError:
    _missing.append("httpx")
try:
    from pynput import keyboard
except ImportError:
    _missing.append("pynput")

if _missing:
    print(f"Faltan dependencias: {', '.join(_missing)}")
    print(f"  pip install {' '.join(_missing)}")
    sys.exit(1)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
TOKEN = os.environ.get("APP_AUTH_TOKEN", "")
SAMPLE_RATE = 44100
MAX_DURATION = 60
_OS = platform.system()  # "Darwin" | "Windows" | "Linux"


def notify(title: str, message: str) -> None:
    msg = message[:300]
    if _OS == "Darwin":
        msg_clean = msg.replace('"', "'").replace("\\", "")
        title_clean = title.replace('"', "'")
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{msg_clean}" with title "{title_clean}" sound name "Morse"'],
                timeout=3, capture_output=True,
            )
        except Exception:
            pass
    else:
        try:
            from plyer import notification
            notification.notify(title=title, message=msg, timeout=4)
        except Exception:
            print(f"[notify] {title}: {msg}")


def beep(freq: int = 880, duration: float = 0.1) -> None:
    try:
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
        tone = (np.sin(2 * np.pi * freq * t) * 0.3 * 32767).astype(np.int16)
        sd.play(tone, SAMPLE_RATE)
        sd.wait()
    except Exception:
        pass


def record_audio(stop_event: threading.Event) -> bytes | None:
    chunks: list[np.ndarray] = []
    start = time.time()

    def callback(indata, frames, time_info, status):
        if stop_event.is_set() or (time.time() - start) > MAX_DURATION:
            raise sd.CallbackStop
        chunks.append(indata.copy())

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                            callback=callback):
            while not stop_event.is_set() and (time.time() - start) < MAX_DURATION:
                time.sleep(0.05)
    except sd.CallbackStop:
        pass
    except Exception as exc:
        print(f"[voice] Error grabando: {exc}")
        return None

    if not chunks:
        return None

    audio = np.concatenate(chunks, axis=0)
    buf = io.BytesIO()
    wavfile.write(buf, SAMPLE_RATE, audio)
    return buf.getvalue()


def transcribe_and_send(audio_bytes: bytes) -> None:
    headers = {"Authorization": f"Bearer {TOKEN}"}

    notify("Orquestador", "Transcribiendo…")
    try:
        resp = httpx.post(
            f"{BACKEND_URL}/api/transcribe",
            headers=headers,
            files={"file": ("voice.wav", audio_bytes, "audio/wav")},
            timeout=30,
        )
        resp.raise_for_status()
        text: str = resp.json().get("text", "").strip()
    except Exception as exc:
        notify("Orquestador ⚠", f"Error al transcribir: {exc}")
        print(f"[voice] Error transcribiendo: {exc}")
        return

    if not text:
        notify("Orquestador", "No entendí el audio.")
        return

    print(f"[voice] Transcript: {text}")
    notify("Orquestador", f'"{text}"')

    try:
        chat_resp = httpx.post(
            f"{BACKEND_URL}/api/chat",
            headers={**headers, "Content-Type": "application/json"},
            json={"message": text},
            timeout=60,
        )
        chat_resp.raise_for_status()
        response_text: str = chat_resp.json().get("text", "").strip()
    except Exception as exc:
        notify("Orquestador ⚠", f"Error al enviar: {exc}")
        print(f"[voice] Error enviando al orquestador: {exc}")
        return

    if response_text:
        preview = response_text[:200].replace("\n", " ")
        notify("Orquestador", preview)
        print(f"[voice] Respuesta: {response_text[:300]}")


class VoiceHotkey:
    def __init__(self):
        self._recording = False
        self._stop_event = threading.Event()
        self._record_thread: threading.Thread | None = None
        self._audio_buf: bytes | None = None
        self._pressed: set = set()
        # macOS usa Cmd, Windows/Linux usa Ctrl
        if _OS == "Darwin":
            self._mod_keys = (keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r)
        else:
            self._mod_keys = (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)

    def _has_mod(self) -> bool:
        return any(k in self._pressed for k in self._mod_keys)

    def _is_trigger(self, key) -> bool:
        try:
            return (hasattr(key, "char") and key.char in ("<", ",", "\\", "|", "º")
                    ) or key == keyboard.KeyCode.from_char("<")
        except Exception:
            return False

    def _is_combo(self, key) -> bool:
        return self._has_mod() and self._is_trigger(key)

    def on_press(self, key):
        self._pressed.add(key)
        if self._is_combo(key) and not self._recording:
            self._start_recording()

    def on_release(self, key):
        self._pressed.discard(key)
        is_mod = key in self._mod_keys
        if (is_mod or self._is_trigger(key)) and self._recording:
            self._stop_recording()

    def _start_recording(self):
        self._recording = True
        self._stop_event.clear()
        beep(880, 0.08)
        mod_name = "Cmd" if _OS == "Darwin" else "Ctrl"
        print(f"[voice] ● Grabando… (soltá {mod_name} para terminar)")
        notify("Orquestador", f"Grabando… soltá {mod_name} para enviar")

        def _run():
            self._audio_buf = record_audio(self._stop_event)

        self._record_thread = threading.Thread(target=_run, daemon=True)
        self._record_thread.start()

    def _stop_recording(self):
        self._recording = False
        self._stop_event.set()
        beep(440, 0.08)
        print("[voice] ■ Grabación terminada")

        if self._record_thread:
            self._record_thread.join(timeout=3)

        audio = self._audio_buf
        self._audio_buf = None

        if audio and len(audio) > 4096:
            threading.Thread(target=transcribe_and_send, args=(audio,), daemon=True).start()
        else:
            print("[voice] Audio demasiado corto, ignorado.")

    def run(self):
        mod_name = "Cmd" if _OS == "Darwin" else "Ctrl"
        combo = f"{mod_name}+<"
        print("=" * 50)
        print("  Orquestador Voice Hotkey activo")
        print(f"  Backend: {BACKEND_URL}")
        print(f"  Sistema: {_OS}")
        print(f"  Mantené {combo} para grabar, soltá para enviar")
        print("  Ctrl+C para salir")
        print("=" * 50)
        notify("Orquestador", f"Voice Hotkey activo — {combo} para grabar")

        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                print("\n[voice] Saliendo.")


if __name__ == "__main__":
    if not TOKEN:
        print("⚠  APP_AUTH_TOKEN no configurado.")
        export_cmd = "set APP_AUTH_TOKEN=<token>" if _OS == "Windows" else "export APP_AUTH_TOKEN=<token>"
        print(f"   {export_cmd}")
        sys.exit(1)

    VoiceHotkey().run()
