<#
.SYNOPSIS
    Arranca el backend FastAPI del asistente (y, con Redis, el proceso trabajador).

.DESCRIPTION
    Sin REDIS_URL (modo por defecto en este equipo): UN proceso uvicorn con el motor
    embebido (Qdrant local, MiniLM, Power BI y MedGemma en hilos de la API). Estado en
    memoria: no usar --workers > 1.

    Con -RedisUrl (o REDIS_URL en el entorno): la API (uvicorn, 1..N procesos) y UN
    proceso trabajador (`python -m backend.worker`), dueño del motor.

    Variables de entorno del motor (MedGemma, Power BI...): las toma del entorno del
    proceso. Si se pasa -ArchivoEntorno, se cargan sus líneas CLAVE=VALOR solo en este
    proceso y sus hijos (el backend nunca abre un .env por su cuenta).

.EXAMPLE
    .\infra\scripts\iniciar_backend.ps1
    .\infra\scripts\iniciar_backend.ps1 -ArchivoEntorno .env -Puerto 8000
    .\infra\scripts\iniciar_backend.ps1 -RedisUrl redis://localhost:6379/0 -Procesos 4
#>
[CmdletBinding()]
param(
    [string]$RedisUrl = $env:REDIS_URL,
    [int]$Puerto = 8000,
    [string]$Anfitrion = "127.0.0.1",
    [int]$Procesos = 1,
    [string]$ArchivoEntorno = "",
    [switch]$Recarga
)

$ErrorActionPreference = "Stop"
$raiz = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
Set-Location $raiz

if ($ArchivoEntorno) {
    foreach ($linea in Get-Content -Encoding utf8 $ArchivoEntorno) {
        $texto = $linea.Trim()
        if (-not $texto -or $texto.StartsWith("#") -or -not $texto.Contains("=")) { continue }
        $partes = $texto.Split("=", 2)
        $valor = $partes[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($partes[0].Trim(), $valor, "Process")
    }
    Write-Host "Variables cargadas desde $ArchivoEntorno (solo este proceso)."
}

$argumentos = @("-m", "uvicorn", "backend.app.main:app", "--host", $Anfitrion, "--port", "$Puerto")
if ($Recarga) { $argumentos += "--reload" }

if ($RedisUrl) {
    $env:REDIS_URL = $RedisUrl
    $env:MOTOR_MODO = "externo"
    Write-Host "Modo Redis: trabajador + API ($Procesos proceso(s))."
    $trabajador = Start-Process -FilePath $python -ArgumentList @("-m", "backend.worker") -PassThru -NoNewWindow
    try {
        if ($Procesos -gt 1) { $argumentos += @("--workers", "$Procesos") }
        & $python @argumentos
    }
    finally {
        if ($trabajador -and -not $trabajador.HasExited) { Stop-Process -Id $trabajador.Id }
    }
}
else {
    if ($Procesos -gt 1) { Write-Warning "Sin Redis solo se admite 1 proceso (estado en memoria): se ignora -Procesos." }
    Remove-Item Env:MOTOR_MODO -ErrorAction SilentlyContinue
    Write-Host "Modo memoria: un proceso, motor embebido. API en http://${Anfitrion}:$Puerto/api/v1/docs"
    & $python @argumentos
}
