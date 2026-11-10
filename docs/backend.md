# Backend FastAPI del asistente

API para el frontend Next.js (y cualquier cliente) que reemplaza a Streamlit (`app.py`, legado congelado).
Contrato: [`specs/006-api-backend/contracts/api-v1.md`](../specs/006-api-backend/contracts/api-v1.md) ·
OpenAPI en vivo: `http://localhost:8000/api/v1/docs` (`/api/v1/openapi.json`).
Diseño y decisiones: [`specs/006-api-backend/plan.md`](../specs/006-api-backend/plan.md).

## Arranque local (sin Redis — el modo de este equipo)

```powershell
# desde la raíz del repositorio, con el .venv del proyecto
.\infra\scripts\iniciar_backend.ps1                       # http://127.0.0.1:8000/api/v1/docs
.\infra\scripts\iniciar_backend.ps1 -ArchivoEntorno .env  # carga MedGemma/Power BI desde un archivo de entorno
# equivalente a mano:
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000
```

- **Un solo proceso** uvicorn. El motor (Qdrant local, MiniLM, Power BI/ADOMD, MedGemma) se arma en un hilo al
  arrancar (puede tardar; `GET /api/v1/salud/listo` responde 503 hasta que esté) y atiende los turnos en hilos de la
  misma API. Todo el estado (conversaciones, turnos, eventos, caché, límites) vive en memoria: se pierde al
  reiniciar y **no** se pueden usar `--workers > 1`.
- El backend **no abre `.env`** por su cuenta: lee variables de entorno. El script las puede cargar de un archivo
  (`-ArchivoEntorno`) solo para ese proceso.
- Los datos (`data/`, `docs_tableros/`) se leen de la raíz del repositorio o de `RAG_RAIZ_DATOS`
  (útil en un worktree sin `data/`).
- Frontend en desarrollo: CORS abierto para `http://localhost:3000` (`CORS_ORIGENES`).

## Procesos, hilos y por qué

| Pieza | Sin Redis (desarrollo) | Con Redis (servidor) |
|---|---|---|
| API (FastAPI, asíncrona) | 1 proceso uvicorn | 1..N procesos uvicorn (`--workers N`), sin estado |
| Motor | hilos dentro de la API (`MOTOR_MODO=auto` → embebido) | **1** proceso `python -m backend.worker` |
| Turnos simultáneos | `MOTOR_INSTANCIAS` (1 por defecto) | ídem, en el trabajador |
| Estado, cola, eventos, caché, límites | memoria | Redis (Streams, hashes, ZSET; ver plan.md) |

- **Qdrant local** admite un solo proceso por carpeta → el motor vive en un único proceso (el trabajador). La API
  puede escalar en procesos porque no lo toca.
- **`QueryEngine` no es seguro entre hilos** (guarda el turno y la conversación en atributos). Cada instancia
  atiende un turno a la vez y el estado de cada conversación se restaura antes del turno y se guarda después
  (`backend/app/services/motor.py`, `SesionPorAtributos`). Así ninguna conversación ve el contexto de otra (en
  Streamlit, con un único motor compartido, sí podía pasar).
- **`turn_slot` (Streamlit) no se usa**: lo reemplaza la piscina. Con `MOTOR_INSTANCIAS=1` hay un turno a la vez
  como hoy; con más, turnos en paralelo (el retriever se comparte con un candado; cada instancia tiene su conexión
  a Power BI). Cada turno corre dentro de `llm_gate.ui_progress`, así las síntesis esperan hueco en MedGemma hasta
  `MEDGEMMA_QUEUE_WAIT_UI` (30 s) en lugar de caer enseguida al resumen extractivo.
- Los turnos esperan en una **cola FIFO compartida**; el trabajador solo toma uno cuando tiene una instancia libre.
  El SSE emite `cola {posicion, en_curso}` mientras espera (la interfaz lo muestra solo en modo diagnóstico).

## Variables de entorno (todas opcionales)

| Variable | Por defecto | Para qué |
|---|---|---|
| `REDIS_URL` | — | Sin valor: modo memoria. Con valor (`redis://host:6379/0`): modo Redis |
| `REDIS_PREFIJO` | `rag` | Prefijo de todas las claves |
| `MOTOR_MODO` | `auto` | `auto` (embebido sin Redis, externo con Redis) · `embebido` · `externo` |
| `MOTOR_INSTANCIAS` | `1` | Instancias del motor (turnos simultáneos); validar con `tools/carga` antes de subirlo |
| `BACKEND_SECRETO` | aleatorio por proceso | Firma HMAC del estado de conversación guardado en Redis. **Obligatorio con Redis** |
| `RAG_RAIZ_DATOS` | raíz del repo | Dónde están `data/` y `docs_tableros/` |
| `CONVERSACION_TTL_S` · `TURNO_TTL_S` · `EVENTOS_TTL_S` | 86400 · 86400 · 3600 | Vida del estado |
| `TURNO_MAX_S` | 600 | Candado de conversación y detección de turnos huérfanos |
| `COLA_MAX` | 200 | Turnos en espera antes de responder 503 |
| `CACHE_HABILITADA` · `CACHE_TTL_S` | `true` · 900 | Caché de respuestas (además se invalida cada día y al cambiar datos/código) |
| `LIMITE_TURNOS` · `LIMITE_TURNOS_IP` · `LIMITE_VENTANA_S` | 12 · 120 · 60 | Turnos por navegador / por IP en la ventana |
| `CONFIAR_PROXY` | `false` | Usar `X-Forwarded-For` (solo detrás de un proxy propio) |
| `CORS_ORIGENES` | `["http://localhost:3000","http://127.0.0.1:3000"]` | JSON |
| `DIAGNOSTICO_HABILITADO` | `true` | `GET /diagnostico/servidor` |
| `CAPACIDADES_EJEMPLOS` | — | JSON con ejemplos fijos para el estado vacío del chat |
| `BACKEND_LOG_NIVEL` | `INFO` | Nivel de log |

Las del motor (MedGemma/Ollama, Power BI, `MEDGEMMA_*`, `LLM_GATE_BACKEND`…) siguen siendo las de siempre.

## Pruebas

```powershell
$env:PYTHONDONTWRITEBYTECODE=1
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests/backend -t .   # almacén, motor, caché, turnos, trabajador
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests/api -t .       # API + SSE de punta a punta
```

Sin red ni servicios: memoria y `fakeredis` (mismo servidor falso para la API asíncrona y el trabajador), motor
doble (`tests/backend/motor_doble.py`) y una prueba con el motor REAL sobre el arnés simulado
(`tests/backend/test_motor_simulado.py`, Power BI/Ollama/Qdrant falsos de `tests/sim`). Las calificaciones de las
pruebas van a una carpeta temporal (`FEEDBACK_DIR`).

## Despliegue con Redis (para el propietario)

Pasos en el servidor (Windows, donde están Power BI/ADOMD, Qdrant y los datos):

1. **Instalar Redis ≥ 6.2** (Streams con grupos y `XAUTOCLAIM`). Opciones en Windows: Memurai (compatible con
   Redis) como servicio, o Redis en otra máquina Linux de la red. Referencia no probada:
   `infra/docker/docker-compose.referencia.yml`. Configuración recomendada: `appendonly yes`,
   `maxmemory 512mb`, `maxmemory-policy volatile-lru` (todas las claves del backend tienen TTL salvo la cola), y
   escuchar solo en la red interna con contraseña (`requirepass`).
2. **Instalar dependencias**: `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
3. **Definir variables** (de sistema o en el servicio, nunca en el código):
   - `REDIS_URL=redis://:CONTRASEÑA@HOST:6379/0`
   - `BACKEND_SECRETO=<64 caracteres aleatorios>` (p. ej. `python -c "import secrets; print(secrets.token_hex(32))"`);
     el mismo valor para la API y el trabajador.
   - `MOTOR_MODO=externo`
   - opcional: `LLM_GATE_BACKEND=redis` (la puerta de MedGemma usa el mismo Redis; ver `src/llm/llm_gate.py`),
     `CORS_ORIGENES=["https://<frontend>"]`, `CONFIAR_PROXY=true` si hay un proxy inverso delante.
   - las del motor (MedGemma, Power BI) como hoy.
4. **Arrancar UN trabajador** (dueño de Qdrant; nunca dos sobre la misma carpeta):
   `.\.venv\Scripts\python.exe -m backend.worker`
   Al arrancar cierra con `error interrumpido` los turnos que un trabajador anterior dejó a medias.
5. **Arrancar la API** con varios procesos:
   `.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 4`
   (o todo junto: `.\infra\scripts\iniciar_backend.ps1 -RedisUrl $env:REDIS_URL -Procesos 4 -Anfitrion 0.0.0.0`).
6. **Comprobar**: `GET /api/v1/salud` → `modo: "redis"`, componentes `ok`; `GET /api/v1/salud/listo` → 200.
7. Como servicio de Windows (p. ej. NSSM), dos servicios: trabajador y API, con reinicio automático. El trabajador
   tarda en estar listo (MiniLM, Power BI); mientras tanto la API acepta turnos y quedan en la cola.

Si Redis no responde al arrancar: con `MOTOR_MODO=externo` la API **no arranca** (error claro en el log; el gestor
de servicios reintenta), porque embeber el motor en varios procesos chocaría con Qdrant. Con `MOTOR_MODO=auto` y un
solo proceso cae al modo memoria con una advertencia.
