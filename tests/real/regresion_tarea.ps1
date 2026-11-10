# Acción para el Programador de tareas de Windows: corre la regresión real
# (tools\manual\regresion_real.py) desde la raíz del checkout principal y deja el log.
# NO crea la tarea; ver la documentación al inicio de tools\manual\regresion_real.py.
# El código de salida de la tarea es el de regresion_real.py (0, 1 o 2).
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root
$env:POWERBI_AUTH = "device_code"
$log = Join-Path $root "tests\real\out_regresion"
New-Item -ItemType Directory -Force $log | Out-Null
& "$root\.venv\Scripts\python.exe" -X utf8 tools\manual\regresion_real.py @args *> (Join-Path $log "ultima_corrida.log")
exit $LASTEXITCODE
