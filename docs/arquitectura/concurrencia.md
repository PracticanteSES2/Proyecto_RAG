# Concurrencia con MedGemma: diagnóstico, medición y opciones

> Rama `agente/carga` · 2026-11-10 · spec: `specs/004-concurrencia-llm/`
> Herramienta: `python -m tools.carga` (salidas en `tools/carga/salidas/`, ignorada por git).

**Resumen para decidir.** Hoy, con un solo proceso Streamlit, 10 personas a la vez **no tumban el
bot ni saturan MedGemma**: el motor está compartido y atiende **un turno a la vez** (`turn_slot`), así
que esas personas hacen fila. El riesgo real hoy es otro: **esperas largas, el aviso «Hay otra consulta en
curso» pasados 120 s y, sobre todo, el contexto de la conversación compartido entre usuarios**. En la
arquitectura nueva (API FastAPI + workers + Redis) los turnos sí irán en paralelo y entonces el cuello de
botella pasa a ser MedGemma: sin cola visible, la síntesis RAG cae al resumen extractivo en cuanto hay más
de `MEDGEMMA_MAX_CONCURRENT` llamadas. Para eso quedan listos: la cola justa con posición (memoria o Redis),
la API para eventos SSE `cola` y la medición real de la capacidad del servidor (sección 4).

## 1. Qué pasa hoy con N usuarios simultáneos (leído del código)

### 1.1 Recorrido de un turno

| Paso | Dónde | Comparte entre sesiones | Seguro entre hilos |
|---|---|---|---|
| Motor, memoria de conversación, contrapreguntas pendientes | `app.py:99` `@st.cache_resource build_system()` → **un único** `QueryEngine` y `ConversationManager` para todas las pestañas/personas; estado en `query_engine.py:141` (`conversation_memory`), `:135` (`_last_success`) | **Sí** | No: por eso `turn_slot` |
| Candado «un turno a la vez» | `app.py:620` `with turn_slot(...)`; `runtime_stats.turn_slot` espera hasta `TURN_WAIT_SECONDS` (120 s, `runtime_stats.py:530`) y luego `TurnBusy` → «Hay otra consulta en curso…» (`app.py:649-658`) | Sí (proceso) | Sí |
| Qdrant local + MiniLM | `HybridRetriever(QDRANT_PATH)` en `build_system` | Sí | Protegido por `turn_slot` |
| Power BI (ADOMD) | `PowerBIProvider` único, conexiones por modelo (`_connections`) | Sí | Protegido por `turn_slot` |
| MedGemma | `src/llm/llm_gate.py` `call_llm`: semáforo de proceso `MEDGEMMA_MAX_CONCURRENT`=3, espera `MEDGEMMA_QUEUE_WAIT`=3 s | Sí | Sí |

### 1.2 Llamadas al LLM por turno

| Uso | Archivo | max_tokens | Tiempo límite | Espera de hueco | ¿Cuándo? |
|---|---|---|---|---|---|
| Síntesis RAG (documental) | `answer_synthesizer.py:19,471-487,534-549` | 600 | 40 s (`RAG_SYNTHESIS_TIMEOUT`) | 3 s | Preguntas documentales: **1 llamada** |
| Reescritura contextual | `contextual_rewriter.py:284,300-313` | 80 | 8 s | 1 s | Seguimientos cortos con memoria («y en urología?»): 0-1 |
| Descripción de opciones | `option_describer.py:45-54,297` | 60 | 15 s | 3 s | Contrapreguntas: **una por opción, hasta 3 en paralelo** (ThreadPool) |
| Intención con LLM | `semantic/intencion_llm.py:50` | 160 | 3 s total | 1 s | **Apagada** por defecto (`INTENCION_LLM=off`) |
| Respuesta numérica de Power BI | — | — | — | — | **0 llamadas** (`synthesize_powerbi` no se usa) |

Un turno típico hace **0 a 2 llamadas** (máximo 3 a la vez con el descriptor). Sin streaming:
`medgemma_provider.py:187` `"stream": False`.

### 1.3 Qué ocurre al saturarse cada pieza

- **Turno** (hoy, el cuello real): la persona n.º k espera ≈ (k-1) × duración de un turno. Si pasa de
  120 s → `TurnBusy` y mensaje de «otra consulta en curso». Antes de este cambio la espera no era FIFO
  (sondeo del candado: entraba quien tuviera suerte); **ahora es FIFO** y la posición es consultable.
- **Puerta del LLM**: sin hueco en 3 s → `llm_saturated` sin llamar; la síntesis RAG usa el **resumen
  extractivo** (`rag_answer_engine.py:155-173`); la reescritura y la intención se omiten; el descriptor usa
  la descripción del catálogo. Con el turno serializado, en un proceso Streamlit esto casi no pasa (máx. 3
  llamadas a la vez = la capacidad).
- **Tiempo límite HTTP** (`medgemma_provider.py` `_client_for`): al vencer se cierra la conexión, Ollama
  deja de generar y se degrada igual que arriba. No queda una petición huérfana ocupando el servidor.
- **Servidor Ollama**: atiende `OLLAMA_NUM_PARALLEL` a la vez; el resto espera en su cola
  (`OLLAMA_MAX_QUEUE`, 512 por defecto; llena → HTTP 503 → `ollama_error`). La espera en esa cola **cuenta
  dentro del tiempo límite** de 40 s.

### 1.4 Qué controla el servidor y qué se puede saber desde el cliente

| Ajuste del servidor | Efecto | ¿Se ve desde el cliente? |
|---|---|---|
| `OLLAMA_NUM_PARALLEL` | Peticiones generando a la vez por modelo | **Indirectamente**: con streaming, el máximo de peticiones generando a la vez (sección 4) |
| `OLLAMA_MAX_QUEUE` | Cola antes de responder 503 | Solo si se llena (503) |
| `num_ctx` por petición × `NUM_PARALLEL` | VRAM del caché KV; si no cabe, Ollama descarga capas a CPU (mucho más lento) o recarga el modelo | Solo por la latencia; el cliente **no** envía `num_ctx` (rige el del servidor) |
| `num_ctx` < prompt | Ollama **recorta la entrada en silencio** | No (el `prompt_eval_count` de la respuesta lo insinúa) |
| VRAM / GPU / otros modelos cargados | Velocidad y recargas | No (`/api/ps` lo diría, pero requiere acceso de administración) |
| Otros clientes del servidor compartido | Ocupan huecos que nuestra puerta no ve | No: nuestra puerta solo cuenta las llamadas de la app |

### 1.5 Los temores, uno por uno

| Temor | ¿Puede pasar hoy? | ¿Ya está contemplado? | Evidencia |
|---|---|---|---|
| **El bot falla** | No se cae. Con mucha fila, quien espera más de 120 s recibe «Hay otra consulta en curso…» y debe repetir. | Parcial: candado liberado siempre en `finally`; ahora la fila es FIFO y la UI puede mostrar la posición. | `app.py:620,649-658`; `runtime_stats.turn_slot` |
| **Responde peor** | Sí, **por el contexto compartido**: un seguimiento («y en urología?») de una persona puede completarse con la pregunta de otra; «Nueva conversación» de una borra el contexto de todas. Además, si el prompt supera `num_ctx` del servidor, Ollama recorta la entrada. | **No** contemplado (requiere estado por sesión: lo resuelve el backend FastAPI con estado de conversación en Redis). | `app.py:99,813-824`; `query_engine.py:141` |
| **Solo da el respaldo (extractivo)** | En Streamlit, raro (turnos en serie). Sí si el servidor está lento (otros clientes) y la síntesis pasa de 40 s. **En la API paralela, sí y mucho** (sección 3). | Sí: degrada rápido y lo dice el razonamiento («MedGemma estaba saturado…»). Nuevo: `ui_progress` convierte saturación en espera visible. | `rag_answer_engine.py:141-173`; `answer_synthesizer.py:534-549` |
| **MedGemma ni lo intenta** | Sí cuando la puerta está llena 3 s (`llm_saturated`), o cuando el turno entero se rechaza por `TurnBusy`. | Sí y queda contado (`STATS`, «saturadas»); `STATS.llm_pressure()` da la presión del último minuto. | `llm_gate.call_llm` |
| **Corta respuestas a la mitad** | Sin streaming nunca se muestra media respuesta: si vence el tiempo se descarta entera. **Sí** puede cortarse por `num_predict` (600 en síntesis, 60 en opciones): Ollama devuelve `done_reason="length"` y antes no se detectaba. | Ahora el proveedor devuelve `done_reason`/`truncated` y la herramienta mide la tasa. Falta decidir qué hacer (subir `max_tokens` o pedir respuestas más cortas). | `medgemma_provider.py` `chat` |

## 2. Qué se implementó

- **Fila justa (FIFO) con posición** para el turno (`turn_slot`) y para MedGemma (`call_llm`), sin
  cambiar contratos: `call_llm` nunca lanza y devuelve los mismos status; `turn_slot` conserva firma,
  `on_wait(waited, since)` y `TurnBusy`.
- **Backend enchufable de la puerta** (`src/llm/gate_backends.py`): `LLM_GATE_BACKEND=memoria` (por
  defecto) o `redis` (`REDIS_URL`). Redis = semáforo distribuido y justo entre procesos/réplicas: tickets
  FIFO (`INCR` + ZSET), préstamos con TTL (un worker caído no deja huecos ocupados para siempre), latido de
  los que esperan (un worker caído esperando no bloquea la fila), reloj del servidor Redis, WATCH/MULTI
  (sin Lua). Si Redis no responde → memoria con advertencia en el log `llm_gate` y reintento cada 30 s.
  `MEDGEMMA_MAX_CONCURRENT` pasa a ser la capacidad **global** (mismo valor en todas las réplicas).
- **Modo con progreso**: `with llm_gate.ui_progress(on_queue=cb):` → la síntesis espera hueco hasta
  `MEDGEMMA_QUEUE_WAIT_UI` (30 s) en lugar de 3 s, la espera no le resta presupuesto a la generación, y `cb`
  recibe `{position, ahead, in_flight, waiting, capacity, waited_s, purpose, titulo}` cada ~0,5 s.
- **API para la UI y el API FastAPI**: `runtime_stats.queue_snapshot()` (turno y LLM del hilo actual),
  `llm_gate.queue_state()`, `llm_gate.evento_cola(estado)` → `{"posicion","en_curso","en_espera","antes",
  "capacidad"}` para el SSE `cola`, `STATS.llm_pressure()` → `{in_flight, waiting, capacity,
  saturated_recent}`, `llm_gate.add_queue_observer(fn)` (títulos «LLM en cola …» para la traza) y campos
  nuevos `turn_queue`, `llm_queue`, `llm_pressure` en `STATS.snapshot()`.
- **`done_reason`/`truncated`/`eval_count`** en la respuesta de `MedGemmaProvider` (detecta cortes por
  `num_predict`).
- **Herramienta** `tools/carga` (ver sección 4).

## 3. Resultados de la simulación

Servidor **simulado** (supuestos a calibrar con la medición real): 3 generaciones a la vez, 20 tokens/s por
petición sola, cada generación simultánea frena a las demás (degradación 0,5), prompt a 1500 tokens/s,
largo de respuesta entre 30 % y 110 % de `max_tokens`. Tiempos en segundos simulados; 2 turnos por usuario.
Archivos: `tools/carga/salidas/carga_*_sim_*.json`.

### 3.1 Extremo a extremo, arquitectura actual (Streamlit: motor compartido, un turno a la vez)

`python -m tools.carga --modo e2e --rampa 1,3,5,10,20 --turnos 2`

| Usuarios | Llamadas LLM | Saturadas | Turno p95 | Espera de turno p95 | Rechazados «otra consulta en curso» | Respaldo extractivo |
|---|---|---|---|---|---|---|
| 1 | 1 | 0 % | 19 s | 0 s | 0 % | 0 % |
| 3 | 11 | 0 % | 44 s | 40 s | 0 % | 0 % |
| 5 | 21 | 0 % | 101 s | 84 s | 0 % | 0 % |
| 10 | 32 | 0 % | 140 s | 121 s | **20 %** | 0 % |
| 20 | 33 | 0 % | 132 s | 120 s | **62 %** | 0 % |

Lectura: MedGemma nunca se satura (los turnos van en fila), la calidad de la respuesta no baja, pero **la
espera crece lineal** y desde ~10 personas a la vez una de cada cinco recibe «otra consulta en curso»
tras 2 minutos. (En e2e el tiempo del motor sin LLM se amplifica por 1/escala: el turno de 1 usuario
sobrestima unos segundos.)

### 3.2 Solo LLM con turnos en paralelo (lo que pasará con la API FastAPI sin cola visible)

`python -m tools.carga --modo llm --perfil mixto --rampa 1,3,5,10,20 --turnos 2` (mezcla: 45 % síntesis,
15 % seguimiento con reescritura, 20 % contrapregunta con 3 descripciones, 20 % numéricas sin LLM)

| Usuarios | Llamadas | OK | p50 | p95 | Saturadas | T. agotado | OK/min | Turno p95 | Respaldo extractivo |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 2 | 8,5 s | 13,7 s | 0 % | 0 % | 7,0 | 16 s | 0 % |
| 3 | 7 | 6 | 9,2 s | 31,7 s | 0 % | 14 % | 6,7 | 40 s | 17 % |
| 5 | 13 | 7 | 8,0 s | 24,5 s | 38 % | 8 % | 8,1 | 37 s | 40 % |
| 10 | 26 | 4 | 7,6 s | 29,6 s | **77 %** | 8 % | 4,1 | 34 s | **60 %** |
| 20 | 56 | 6 | 16,1 s | 31,5 s | **88 %** | 2 % | 6,3 | 31 s | **55 %** |

Con `--espera-ui 30` (cola visible: la síntesis espera hasta 30 s en vez de 3 s):

| Usuarios | Saturadas | p50 | p95 | Turno p95 | Respaldo extractivo |
|---|---|---|---|---|---|
| 5 | 31 % | 23,8 s | 44,4 s | 47 s | 20 % |
| 10 | 58 % | 47,0 s | 62,3 s | 64 s | **35 %** |
| 20 | 82 % | 44,9 s | 59,8 s | 57 s | 48 % |

Lectura: el servidor (supuesto) da **~4-8 respuestas por minuto en total**; eso no lo cambia ninguna cola.
La cola visible **cambia respaldo por espera** (de 60 % a 35 % de respaldo con 10 personas, a cambio de ~1
minuto de espera), y la reescritura y las descripciones (espera explícita de 1-3 s, opcionales) siguen
cayendo a reglas/catálogo, que es lo deseado. Con muchos usuarios a la vez, la única salida de fondo es
**más capacidad de generación** o **menos llamadas** (caché, respuestas más cortas).

## 4. Medición real (pendiente de ejecutar)

La corrida contra el servidor real **no se ejecutó**: el control de permisos de Claude Code la bloqueó
(«interferir con cargas de trabajo» de un servidor compartido). Queda lista para que el usuario la corra
(o autorice la regla de permisos). Es corta: 58 peticiones de 64 tokens con texto fijo.

```powershell
cd C:\Users\ad6708\Documents\Proyecto_RAG
$env:PYTHONDONTWRITEBYTECODE='1'
# 1) Capacidad del servidor (sin la puerta de la app, con streaming para ver el primer token):
'SI' | .venv\Scripts\python.exe -X utf8 -c "import sys; sys.path.insert(0, r'.claude\worktrees\carga'); from tools.carga.__main__ import main; sys.exit(main(['--real','--modo','llm','--perfil','sonda','--sin-puerta','--streaming','--rampa','1,2,3,5,8,10','--turnos','2','--parar-si-error','0.3','--etiqueta','real_sonda']))"
# 2) Solo si hasta 10 fue estable: --rampa 15,20 con el mismo comando.
# 3) Latencia real de la síntesis (pocas llamadas largas, por la puerta como la app):
'SI' | .venv\Scripts\python.exe -X utf8 -c "import sys; sys.path.insert(0, r'.claude\worktrees\carga'); from tools.carga.__main__ import main; sys.exit(main(['--real','--modo','llm','--perfil','sintesis','--streaming','--rampa','1,3','--turnos','1','--etiqueta','real_sintesis']))"
```

(Cuando la rama se fusione basta `python -m tools.carga --real ...` desde la raíz.) El `.env` lo lee el
propio `MedGemmaProvider`; la herramienta no lo abre ni imprime el token. Pide escribir `SI`, hace un
`healthcheck` antes y se detiene si un escalón pasa de 30 % de errores + tiempos agotados.

**Cómo leer la corrida 1** (columna `paralelo` y JSON `paralelismo_observado`):

- `generando_max` se queda en **P** aunque haya 8 o 10 usuarios → el servidor genera **P a la vez**
  (`OLLAMA_NUM_PARALLEL` efectivo); el resto espera en la cola de Ollama: se ve como `1er tok p95` ≈ varias
  duraciones de generación.
- Duración por petición (`duration_s - ttft`) con k simultáneas ÷ con 1 → **degradación** por concurrencia
  (calibra `--degradacion` del simulador). Tokens/s con 1 usuario = 64 / (duración - ttft) → calibra `--tps`.
- Respuestas 503 → `OLLAMA_MAX_QUEUE` lleno. Tiempos agotados con 1 usuario → servidor ocupado por otros.

Después, repetir la simulación con los valores calibrados
(`--capacidad P --tps T --degradacion D`) para proyectar 10-50 usuarios sin volver a cargar el servidor.

### 4.1 Recomendación provisional (confirmar con la corrida 1)

| Ajuste | Dónde | Recomendación |
|---|---|---|
| `MEDGEMMA_MAX_CONCURRENT` | app / API (todas las réplicas, global con Redis) | **= P medido** (hoy 3, coherente con «se satura con más de 3»). Ni más (las de más esperan en la cola de Ollama consumiendo su tiempo límite sin que la UI lo sepa) ni menos (se desperdicia GPU). Si el servidor lo usan otras aplicaciones, P menos lo que ellas usan en hora pico. |
| `OLLAMA_NUM_PARALLEL` | servidor (administrador) | Subirlo solo si la VRAM alcanza `num_ctx × NUM_PARALLEL` de caché KV **sin descargar capas a CPU**; medir con la corrida 1 que los tokens/s totales suben. Si la degradación es ≈ 1 (cada una va a 1/k), subirlo no aporta: hace falta otra GPU/réplica. |
| `OLLAMA_MAX_QUEUE` | servidor | Bajarlo (p. ej. 16-32) para que una sobrecarga falle rápido con 503 en lugar de esperas mudas; la cola justa y visible la lleva la API. |
| `OLLAMA_CONTEXT_LENGTH` / `num_ctx` | servidor | ≥ 4096, idealmente 8192: la síntesis envía ~2.400-2.800 tokens de prompt + 600 de salida (+ historial). Con 2048 Ollama recorta la entrada en silencio. |
| `OLLAMA_KEEP_ALIVE` | servidor | Largo (p. ej. 30m-24h) en horario laboral: evita recargas en frío (la app ya pide `keep_alive` 10m). |
| `OLLAMA_MAX_LOADED_MODELS` | servidor | Si el servidor sirve otros modelos, que MedGemma no sea desalojado por ellos. |

## 5. Opciones ordenadas por costo/beneficio

| # | Opción | Costo | Beneficio | Cuándo |
|---|---|---|---|---|
| 1 | **Ajustes de Ollama** (tabla 4.1) y `MEDGEMMA_MAX_CONCURRENT` = capacidad medida | Muy bajo (variables del servidor) | Evita recortes de contexto, recargas en frío y esperas mudas | Ya, tras la corrida real |
| 2 | **Cola justa visible** (hecha) + mostrar posición en la UI/SSE | Bajo (consumir la API) | Cambia «respaldo»/«otra consulta en curso» por espera con posición | Ya (UI de progreso / backend) |
| 3 | **Estado de conversación por sesión** (en la API, en Redis) | Medio (lo hace el agente del backend) | Elimina la mezcla de contexto entre usuarios y permite turnos en paralelo | Imprescindible para «todo el hospital» |
| 4 | **Caché de respuestas** por pregunta normalizada + versión de datos/documentos | Medio | Las documentales repetidas no llaman a MedGemma (0 s, 0 GPU). Las numéricas no la necesitan (no usan LLM) | Con varias dependencias preguntando lo mismo |
| 5 | **Streaming de tokens** al navegador (SSE) | Medio (proveedor `stream=True`, API, frontend) | El primer token llega en ~1-2 s (ver `1er tok`) aunque la respuesta tarde 20 s; no aumenta la capacidad | Con la nueva UI Next.js |
| 6 | **Respuestas más cortas / menos llamadas** (`max_tokens` 600 → 350 donde baste; 1 llamada para todas las opciones) | Bajo-medio | Más respuestas por minuto con la misma GPU (la duración es casi proporcional a los tokens) | Si la medición confirma que la generación domina |
| 7 | **Más capacidad**: otra GPU/réplica de MedGemma detrás de un balanceador | Alto (hardware) | Es lo único que sube las respuestas por minuto de verdad | Si con 1-6 la espera sigue alta en hora pico |

## 6. Redis en la arquitectura objetivo (API FastAPI + workers + Redis)

Con un solo proceso Streamlit, Redis era innecesario (un semáforo de proceso coordina todo). La decisión ya
tomada (API FastAPI con varios workers y un frontend Next.js, usado por todo el hospital) **sí lo
justifica**, porque aparecen varios procesos/réplicas que deben ponerse de acuerdo:

| Uso de Redis | Dueño | Por qué hace falta |
|---|---|---|
| **Semáforo/cola justa del LLM entre workers** (`LLM_GATE_BACKEND=redis`) | Esta rama (hecho) | Con 4 workers y un semáforo de 3 por proceso se mandarían hasta 12 llamadas al servidor; con Redis el límite es global, FIFO y con posición |
| Cola de turnos, estado de conversación por sesión | Backend FastAPI | Cada persona con su contexto; cualquier worker atiende cualquier turno |
| Caché de respuestas (pregunta normalizada + versión de datos) | Backend FastAPI | Compartida por todos los workers |
| Límite de peticiones por usuario/dependencia | Backend FastAPI | Evita que una dependencia acapare la GPU |

Lo que Redis **no** hace: no aumenta la capacidad de MedGemma (sección 3.2): ordena la espera, la hace
visible y evita trabajo repetido. Si Redis cae, la puerta sigue funcionando en memoria (cada worker con su
propio límite: conviene entonces `MEDGEMMA_MAX_CONCURRENT` = P ÷ nº de workers como respaldo) y lo avisa en
el log. Una cola persistente con workers dedicados al LLM (p. ej. Redis Streams) solo aporta si se quieren
trabajos que sobrevivan a reinicios o respuestas diferidas; para respuestas interactivas basta el semáforo
justo + SSE.

Contrato para el backend (SSE `cola`): la llamada al LLM corre en un hilo del threadpool; abrir
`ui_progress(on_queue=cb)` en ese hilo y en `cb` hacer
`loop.call_soon_threadsafe(cola.put_nowait, llm_gate.evento_cola(evento))`; al terminar llega un evento con
`done: True`. Variables: `LLM_GATE_BACKEND`, `REDIS_URL`, `LLM_GATE_LEASE_S` (120), `LLM_GATE_WAITER_TTL_S`
(10), `LLM_GATE_POLL_S` (0,2), `MEDGEMMA_QUEUE_WAIT_UI` (30).

## 7. Lo que le toca decidir al usuario

1. **Correr la medición real** (sección 4) o autorizarla en los permisos, y pasar al administrador del
   servidor la tabla 4.1 con el P medido.
2. **Espera máxima aceptable** en hora pico (define `MEDGEMMA_QUEUE_WAIT_UI` y el tiempo de espera de
   turno del backend): ¿30 s, 60 s? Más espera = menos respaldo extractivo.
3. **¿Respaldo extractivo o espera?** cuando la fila es larga (p. ej. respaldo inmediato si hay más de N
   antes).
4. **Hardware**: si la medición confirma ~P=3 y degradación alta, «todo el hospital» en hora pico necesitará
   una segunda GPU/réplica; Redis y la caché solo lo posponen.
5. **`max_tokens` de la síntesis** (600): medir cuántas salen `truncated` y decidir si se acortan las
   respuestas o se sube el límite.
