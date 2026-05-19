# start.ps1 — Agente Orquestador para Windows
# Ejecutar con: powershell -ExecutionPolicy Bypass -File start.ps1

$ErrorActionPreference = "Stop"
$DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $DIR

Write-Host "=== Agente Orquestador ===" -ForegroundColor Cyan

# 1. Docker
Write-Host "▶ Levantando Docker..." -ForegroundColor Yellow
docker compose up -d
Write-Host "  Esperando que los servicios esten listos..."
Start-Sleep -Seconds 10

# 2. Health check
Write-Host "▶ Verificando backend..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 10
    Write-Host "  OK Backend" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Backend no responde. Revisa: docker compose logs backend" -ForegroundColor Red
    exit 1
}

# 3. Leer token del .env
$envLines = Get-Content "$DIR\.env" | Where-Object { $_ -match "^APP_AUTH_TOKEN=" }
$TOKEN = ($envLines -replace "^APP_AUTH_TOKEN=", "").Trim()
if (-not $TOKEN) {
    Write-Host "  ERROR: APP_AUTH_TOKEN no encontrado en .env" -ForegroundColor Red
    exit 1
}

# 4. Frontend en ventana nueva
Write-Host "▶ Iniciando frontend..." -ForegroundColor Yellow
$frontendProc = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/k cd /d `"$DIR\frontend`" && npm run dev" `
    -PassThru -WindowStyle Normal
Write-Host "  OK Frontend en http://localhost:3000" -ForegroundColor Green

# 5. Hotkey de voz en ventana nueva
Write-Host "▶ Iniciando hotkey de voz (Ctrl+< para grabar)..." -ForegroundColor Yellow
$env:BACKEND_URL = "http://localhost:8000"
$env:APP_AUTH_TOKEN = $TOKEN
$voiceProc = Start-Process -FilePath "python" `
    -ArgumentList "`"$DIR\scripts\voice_hotkey.py`"" `
    -PassThru -WindowStyle Minimized
Write-Host "  OK Hotkey activa" -ForegroundColor Green

# 6. Abrir browser
Start-Sleep -Seconds 3
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "Sistema iniciado:" -ForegroundColor Cyan
Write-Host "  Backend:  http://localhost:8000"
Write-Host "  Frontend: http://localhost:3000"
Write-Host "  Hotkey:   Ctrl+< para grabar voz"
Write-Host ""
Write-Host "Presiona Enter para detener frontend y hotkey." -ForegroundColor Gray
Write-Host "Docker sigue corriendo hasta que hagas: docker compose down" -ForegroundColor Gray
Write-Host ""

Read-Host "Enter para detener"

# Limpiar
if ($frontendProc -and !$frontendProc.HasExited) {
    Stop-Process -Id $frontendProc.Id -Force -ErrorAction SilentlyContinue
}
if ($voiceProc -and !$voiceProc.HasExited) {
    Stop-Process -Id $voiceProc.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "Frontend y hotkey detenidos." -ForegroundColor Yellow
Write-Host "Para apagar Docker: docker compose down" -ForegroundColor Gray
