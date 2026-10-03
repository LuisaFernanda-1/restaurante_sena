# ============================================================
#  instalar.ps1 — Instalación de Restaurante SENA en Windows
#
#  1. Verifica Python 3.12 o superior.
#  2. Crea el entorno virtual backend\.venv e instala las dependencias.
#  3. Crea backend\.env (si no existe) con una SECRET_KEY aleatoria, el
#     puerto de MySQL de XAMPP y la IP de este computador.
#  4. Crea la base de datos SOLO si todavía no existe (nunca borra datos).
#
#  Uso:  powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
# ============================================================
$ErrorActionPreference = 'Stop'
$raiz    = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $raiz 'backend'
$venv    = Join-Path $backend '.venv'
$python  = Join-Path $venv 'Scripts\python.exe'
$envFile = Join-Path $backend '.env'
$mysqlExe = 'C:\xampp\mysql\bin\mysql.exe'

function Paso([string]$texto) { Write-Host ''; Write-Host "==> $texto" -ForegroundColor Cyan }
function Fallo([string]$texto) { Write-Host "ERROR: $texto" -ForegroundColor Red; Read-Host 'Presione Enter para cerrar'; exit 1 }

# ---------- 1. Python ----------
Paso 'Buscando Python 3.12 o superior'
$pythonExe = $null; $pythonArgs = @()
foreach ($candidato in @(@('py', '-3'), @('python'))) {
    try {
        $extra = @(); if ($candidato.Length -gt 1) { $extra = $candidato[1..($candidato.Length - 1)] }
        # Devuelve, por ejemplo, 313 para Python 3.13 (sin comillas: más seguro en PowerShell 5.1)
        $numero = & $candidato[0] @extra -c "import sys; print(sys.version_info[0] * 100 + sys.version_info[1])" 2>$null
        if ($numero -and ([int]$numero -ge 312)) { $pythonExe = $candidato[0]; $pythonArgs = $extra; break }
    } catch { }
}
if (-not $pythonExe) { Fallo 'No se encontró Python 3.12 o superior. Instálelo desde https://www.python.org (marque "Add python.exe to PATH").' }
Write-Host ("Python {0}.{1} encontrado." -f [math]::Floor([int]$numero / 100), ([int]$numero % 100))

# ---------- 2. Entorno virtual y dependencias ----------
if (-not (Test-Path $python)) {
    Paso 'Creando el entorno virtual (backend\.venv)'
    & $pythonExe @pythonArgs -m venv $venv
    if ($LASTEXITCODE -ne 0) { Fallo 'No se pudo crear el entorno virtual.' }
}
Paso 'Instalando dependencias (requiere internet la primera vez)'
& $python -m pip install --upgrade pip --quiet
& $python -m pip install -r (Join-Path $backend 'requirements.txt') --quiet
if ($LASTEXITCODE -ne 0) { Fallo 'No se pudieron instalar las dependencias.' }

# ---------- 3. Archivo .env ----------
if (Test-Path $envFile) {
    Paso 'backend\.env ya existe: no se modifica'
} else {
    Paso 'Creando backend\.env'
    $secreto = & $python -c 'import secrets; print(secrets.token_hex(32))'
    # Puerto de MySQL configurado en XAMPP
    $puerto = '3306'
    $myIni = 'C:\xampp\mysql\bin\my.ini'
    if (Test-Path $myIni) {
        $linea = Select-String -Path $myIni -Pattern '^\s*port\s*=\s*(\d+)' | Select-Object -First 1
        if ($linea) { $puerto = $linea.Matches[0].Groups[1].Value }
    }
    # IP de este computador en la red local
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
           Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
           Select-Object -First 1).IPAddress
    if (-not $ip) { $ip = 'localhost' }
    $contenido = Get-Content (Join-Path $backend '.env.example') -Encoding UTF8
    $contenido = $contenido -replace '^DB_PORT=.*', "DB_PORT=$puerto"
    $contenido = $contenido -replace '^SECRET_KEY=.*', "SECRET_KEY=$secreto"
    $contenido = $contenido -replace '^SERVER_URL=.*', "SERVER_URL=http://${ip}:8000"
    $utf8SinBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllLines($envFile, $contenido, $utf8SinBom)
    Write-Host "Creado con DB_PORT=$puerto y SERVER_URL=http://${ip}:8000"
    Write-Host 'Si MySQL tiene contraseña, escríbala en DB_PASSWORD dentro de backend\.env.' -ForegroundColor Yellow
}

# ---------- 4. Base de datos ----------
Paso 'Revisando la base de datos'
if (-not (Test-Path $mysqlExe)) {
    Write-Host "No se encontró $mysqlExe. Importe backend\restaurante_sena_completo.sql desde phpMyAdmin (vea el README)." -ForegroundColor Yellow
} else {
    $config = @{}
    Get-Content $envFile -Encoding UTF8 | ForEach-Object {
        if ($_ -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $config[$matches[1]] = $matches[2].Trim() }
    }
    $env:MYSQL_PWD = $config['DB_PASSWORD']
    $argsBase = @('-h', $config['DB_HOST'], '-P', $config['DB_PORT'], '-u', $config['DB_USER'], '-N', '--default-character-set=utf8mb4')
    $existe = & $mysqlExe @argsBase -e "SHOW DATABASES LIKE '$($config['DB_NAME'])'" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'MySQL no responde. Inicie MySQL en el panel de XAMPP y vuelva a ejecutar este script.' -ForegroundColor Yellow
    } elseif ($existe) {
        Write-Host "La base '$($config['DB_NAME'])' ya existe: no se toca."
        Write-Host 'Si viene de la versión anterior, actualícela con:  backend\.venv\Scripts\python.exe backend\migrar.py' -ForegroundColor Yellow
    } else {
        $nombreBd = $config['DB_NAME']
        if ($nombreBd -notmatch '^[A-Za-z0-9_]{1,64}$') { Fallo "DB_NAME inválido en backend\.env: $nombreBd" }
        Write-Host "Creando la base '$nombreBd'..."
        # El script SQL usa el nombre restaurante_sena: se cambia por DB_NAME para
        # no crear (ni borrar) una base distinta a la configurada.
        $sql = Get-Content (Join-Path $backend 'restaurante_sena_completo.sql') -Raw -Encoding UTF8
        $sql = $sql -replace '(?m)^(DROP DATABASE IF EXISTS|CREATE DATABASE|USE)\s+restaurante_sena\b', "`$1 $nombreBd"
        # PowerShell 5.1 envía el texto a los programas externos en ASCII y dañaría
        # las tildes y los emojis: se fuerza UTF-8 (sin BOM).
        $OutputEncoding = New-Object System.Text.UTF8Encoding $false
        $sql | & $mysqlExe @argsBase
        if ($LASTEXITCODE -ne 0) { Fallo 'No se pudo crear la base de datos.' }
        Write-Host 'Base de datos creada.' -ForegroundColor Green
    }
    Remove-Item Env:\MYSQL_PWD -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host 'Instalación terminada.' -ForegroundColor Green
Write-Host 'Para iniciar el sistema: doble clic en scripts\iniciar_servidor.bat'
Read-Host 'Presione Enter para cerrar'
