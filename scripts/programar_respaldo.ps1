# ============================================================
#  programar_respaldo.ps1 — Programa el respaldo diario automático
#
#  Crea una tarea en el Programador de tareas de Windows que ejecuta
#  scripts\respaldo.py todos los días a la hora indicada (23:30 por
#  defecto). Ejecútelo una sola vez, como Administrador:
#      powershell -ExecutionPolicy Bypass -File scripts\programar_respaldo.ps1
#      powershell -ExecutionPolicy Bypass -File scripts\programar_respaldo.ps1 -Hora 22:00
# ============================================================
param([string]$Hora = '23:30')
$ErrorActionPreference = 'Stop'
$raiz   = Split-Path -Parent $PSScriptRoot
$python = Join-Path $raiz 'backend\.venv\Scripts\python.exe'
$script = Join-Path $raiz 'scripts\respaldo.py'

if (-not (Test-Path $python)) { Write-Host 'Ejecute primero scripts\instalar.ps1' -ForegroundColor Red; exit 1 }

$accion  = New-ScheduledTaskAction -Execute $python -Argument "`"$script`"" -WorkingDirectory $raiz
$disparo = New-ScheduledTaskTrigger -Daily -At $Hora
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
Register-ScheduledTask -TaskName 'Restaurante SENA - Respaldo diario' -Action $accion -Trigger $disparo `
    -Settings $ajustes -Description 'Respaldo comprimido de la base de datos (conserva 30 días)' -Force | Out-Null

Write-Host "Listo: el respaldo se hará todos los días a las $Hora en la carpeta respaldos\." -ForegroundColor Green
Write-Host 'Puede verlo o cambiarlo en: Inicio > Programador de tareas > "Restaurante SENA - Respaldo diario".'
