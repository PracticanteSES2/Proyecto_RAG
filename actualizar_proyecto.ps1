# ============================================================
# Actualiza el proyecto con lo último de la rama `desarrollo`
# y deja el RAG listo para probar.
#
# Uso (desde la carpeta del proyecto, en PowerShell):
#     powershell -ExecutionPolicy Bypass -File .\actualizar_proyecto.ps1
#
# Opciones:
#     -SinSincronizar   no vuelve a descargar la metadata de Power BI
#     -Rama otra        usa otra rama en vez de `desarrollo`
#
# Qué hace:
#   1. Trae y aplica los cambios de GitHub (rama desarrollo).
#   2. Instala dependencias nuevas en el entorno virtual.
#   3. Revisa que el .env tenga las variables necesarias (no muestra valores).
#   4. Regenera todo el RAG con tools\update_rag.py: metadata de Power BI, catálogos,
#      enlaces «Abrir en Power BI» y la documentación de docs_tableros/.
#   5. Le dice cómo abrir la aplicación.
# Solo lee de Power BI: no modifica tableros, modelos ni bases de datos.
# ============================================================
param(
    [switch]$SinSincronizar,
    [string]$Rama = "desarrollo"
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Paso($texto) { Write-Host "`n=== $texto ===" -ForegroundColor Cyan }
function Falla($texto) { Write-Host "`nERROR: $texto" -ForegroundColor Red; exit 1 }

# ------------------------------------------------------------
Paso "1/5 Traer los cambios de GitHub (rama $Rama)"
git fetch origin
if ($LASTEXITCODE -ne 0) { Falla "git fetch falló. Revisa la conexión o el acceso a GitHub." }

$cambiosLocales = git status --porcelain --untracked-files=no
if ($cambiosLocales) {
    Write-Host "Tienes cambios locales sin guardar:" -ForegroundColor Yellow
    Write-Host $cambiosLocales
    Write-Host "Se guardan con 'git stash' para poder actualizar (recupéralos luego con 'git stash pop')." -ForegroundColor Yellow
    git stash push -m "antes de actualizar_proyecto $(Get-Date -Format s)"
    if ($LASTEXITCODE -ne 0) { Falla "No se pudieron guardar los cambios locales con git stash." }
}

git checkout $Rama
if ($LASTEXITCODE -ne 0) { Falla "No se pudo cambiar a la rama $Rama." }
git pull --ff-only origin $Rama
if ($LASTEXITCODE -ne 0) { Falla "git pull falló (¿tu rama local tiene commits propios?). Resuélvelo y vuelve a ejecutar." }
Write-Host ("Versión actual: " + (git log --oneline -1))

# ------------------------------------------------------------
Paso "2/5 Entorno virtual y dependencias"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "No existe .venv: se crea." -ForegroundColor Yellow
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Falla "No se pudo crear el entorno virtual (.venv)." }
}
& $python -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { Falla "pip install -r requirements.txt falló." }

# ------------------------------------------------------------
Paso "3/5 Revisar el .env (solo si existen las variables; no se muestran valores)"
if (-not (Test-Path ".env")) { Falla "No existe el archivo .env en la carpeta del proyecto." }
$revision = @'
from dotenv import dotenv_values
v = dotenv_values(".env")
obligatorias = ["POWERBI_XMLA_ENDPOINT", "ADOMD_PATH", "IDENTITY_PATH", "MEDGEMMA_BASE_URL"]
recomendadas = ["MEDGEMMA_MODEL", "MEDGEMMA_API_KEY"]
faltan = [k for k in obligatorias if not v.get(k)]
for k in obligatorias + recomendadas:
    print(f"  {k}: {'definida' if v.get(k) else 'NO definida'}")
if not v.get("MEDGEMMA_API_KEY"):
    print("  AVISO: sin MEDGEMMA_API_KEY el servidor de MedGemma responde 401 y las respuestas salen sin redaccion del modelo.")
raise SystemExit(1 if faltan else 0)
'@
$revision | & $python -X utf8 -
if ($LASTEXITCODE -ne 0) { Falla "Faltan variables obligatorias en el .env (ver arriba)." }

# ------------------------------------------------------------
Paso "4a Sesion de Power BI para los enlaces del boton «Abrir en Power BI»"
# El catalogo de enlaces se descarga con la API REST de Power BI y necesita
# una sesion con codigo de dispositivo (no usa la ventana de login de ADOMD).
& $python -X utf8 -m src.providers.powerbi_token estado
if ($LASTEXITCODE -ne 0) {
    Write-Host "No hay sesion guardada: abre https://login.microsoft.com/device y escribe el codigo que aparece abajo." -ForegroundColor Yellow
    & $python -X utf8 -m src.providers.powerbi_token login
    if ($LASTEXITCODE -ne 0) {
        Write-Host "AVISO: no se completo el inicio de sesion; el boton «Abrir en Power BI» no tendra enlaces." -ForegroundColor Yellow
    }
}

# ------------------------------------------------------------
Paso "4/5 Regenerar el RAG (metadata, catálogos, enlaces e índice)"
Write-Host "Puede abrirse la ventana de inicio de sesión de Microsoft: entra con tu cuenta de Power BI." -ForegroundColor Yellow
Write-Host "Este paso puede tardar varios minutos (embeddings de la documentación)."
$argumentos = @("-X", "utf8", "tools\update_rag.py", "--skip-import")
if ($SinSincronizar) { $argumentos += "--skip-sync" } else { $argumentos += "--force-sync" }
& $python @argumentos
if ($LASTEXITCODE -ne 0) { Falla "tools\update_rag.py falló en algún paso (ver el mensaje de arriba)." }

# ------------------------------------------------------------
Paso "5/5 Listo"
if (Test-Path "data\catalog\report_links.json") {
    Write-Host "Enlaces del boton «Abrir en Power BI»: OK (data\catalog\report_links.json)." -ForegroundColor Green
} else {
    Write-Host "AVISO: no se generaron los enlaces del boton «Abrir en Power BI»." -ForegroundColor Yellow
    Write-Host "  Ejecuta:  .venv\Scripts\python.exe -m src.providers.powerbi_token login" -ForegroundColor Yellow
    Write-Host "  y luego:  .venv\Scripts\python.exe -X utf8 tools\sync_powerbi_links.py" -ForegroundColor Yellow
}
Write-Host "Si la aplicación estaba abierta, CIÉRRALA (Ctrl+C en su terminal) y ábrela de nuevo:" -ForegroundColor Green
Write-Host "    .venv\Scripts\python.exe -m streamlit run app.py" -ForegroundColor Green
Write-Host "Sin reiniciar la app no se ven los cambios (botón «Abrir en Power BI», nuevas respuestas)."
