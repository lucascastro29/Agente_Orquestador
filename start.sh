#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== Agente Orquestador ==="

# 1. Docker
echo "▶ Levantando Docker..."
docker compose up -d
echo "  Esperando que los servicios estén listos..."
sleep 8

# 2. Health check
if curl -sf http://localhost:8000/health > /dev/null; then
  echo "  ✓ Backend OK"
else
  echo "  ✗ Backend no responde — revisá: docker compose logs backend"
  exit 1
fi

# 3. Frontend
echo "▶ Iniciando frontend..."
cd "$DIR/frontend"
npm run dev &
FRONTEND_PID=$!
echo "  ✓ Frontend en http://localhost:3000 (PID $FRONTEND_PID)"

# 4. Hotkey de voz
TOKEN=$(grep APP_AUTH_TOKEN "$DIR/.env" | cut -d= -f2)
echo "▶ Iniciando hotkey de voz (Cmd+< para grabar)..."
BACKEND_URL=http://localhost:8000 APP_AUTH_TOKEN="$TOKEN" python3 "$DIR/scripts/voice_hotkey.py" &
VOICE_PID=$!
echo "  ✓ Hotkey activa (PID $VOICE_PID)"

echo ""
echo "Sistema iniciado:"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo ""
echo "Ctrl+C para detener frontend y hotkey (Docker sigue corriendo)"
echo "Para apagar Docker: docker compose down"
echo ""

# Esperar y limpiar al hacer Ctrl+C
trap "kill $FRONTEND_PID $VOICE_PID 2>/dev/null; echo 'Frontend y hotkey detenidos.'" EXIT
wait $FRONTEND_PID
