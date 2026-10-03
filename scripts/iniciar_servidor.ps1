# ============================================================
#  iniciar_servidor.ps1 — Inicia Restaurante SENA (Waitress, 0.0.0.0:8000)
#
#  Uso: clic derecho > "Ejecutar con PowerShell", doble clic en
#  iniciar_servidor.bat, o desde PowerShell:
#      powershell -ExecutionPolicy Bypass -File scripts\iniciar_servidor.ps1
# ============================================================
$ErrorActionPreference = 'Stop'
try { $Host.UI.RawUI.WindowTitle = 'Restaurante SENA - Servidor' } catch { }

$raiz    = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $raiz 'backend'
$python  = Join-Path $backend '.venv\Scripts\python.exe'
$envFile = Join-Path $backend '.env'

function Salir-ConError([string]$mensaje) {
    Write-Host ''
    Write-Host "ERROR: $mensaje" -ForegroundColor Red
    Write-Host ''
    Read-Host 'Presione Enter para cerrar'
    exit 1
}

if (-not (Test-Path $python)) {
    Salir-ConError 'No se encontró el entorno de Python. Ejecute primero scripts\instalar.ps1 (vea el README).'
}
if (-not (Test-Path $envFile)) {
    Salir-ConError 'No existe backend\.env. Copie backend\.env.example como backend\.env y complételo.'
}

# Leer DB_HOST y DB_PORT del .env para verificar que MySQL esté encendido
$config = @{}
Get-Content $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $config[$matches[1]] = $matches[2].Trim() }
}
$dbHost = if ($config['DB_HOST']) { $config['DB_HOST'] } else { '127.0.0.1' }
$dbPort = if ($config['DB_PORT']) { [int]$config['DB_PORT'] } else { 3306 }

$mysqlActivo = $false
try {
    $cliente = New-Object System.Net.Sockets.TcpClient
    $intento = $cliente.BeginConnect($dbHost, $dbPort, $null, $null)
    if ($intento.AsyncWaitHandle.WaitOne(3000) -and $cliente.Connected) { $mysqlActivo = $true }
    $cliente.Close()
} catch { $mysqlActivo = $false }

if (-not $mysqlActivo) {
    Salir-ConError "MySQL no responde en ${dbHost}:${dbPort}. Abra el panel de XAMPP y pulse 'Start' en MySQL."
}

Write-Host 'MySQL encendido. Iniciando el servidor...' -ForegroundColor Green
Set-Location $backend
& $python servidor.py
$codigo = $LASTEXITCODE
if ($codigo -ne 0) { Salir-ConError "El servidor se detuvo (código $codigo). Revise logs\servidor.log." }
