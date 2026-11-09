# Portero conversacional — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Responder saludo/agradecimiento/despedida/«¿cómo estás?», «¿quién eres?» y «¿qué puedes hacer?» sin buscar, sin interceptar nunca una pregunta real del dominio.

**Architecture:** Módulo puro `src/chatbot/portero.py` (reglas + guardas + similitud MiniLM inyectada + textos de respuesta) llamado desde `QueryEngine.process()` tras la normalización. Nueva ruta `conversacion`; el turno no entra en `conversation_memory`.

**Tech Stack:** Python 3, unittest, sentence-transformers (MiniLM ya cargado), Streamlit.

**Spec:** `docs/superpowers/specs/2026-11-09-portero-conversacional-design.md`

## Global Constraints

- Power BI y BD de producción: solo lectura; el portero no consulta nada.
- Nada de datos de pacientes en salidas, logs o commits. `.env` solo lo edita el usuario; no cargarlo.
- Sin dependencias, modelos ni llamadas a Ollama nuevas; respuestas fijas sin LLM.
- Anti-objetivo principal: 0 preguntas reales interceptadas (bancos y banco del portero).
- Calibrar umbral/margen SOLO con `tests/portero/banco_portero.json` y `tests/real/banco_real.json`; holdout 1, holdout 2 y multi-turno solo como prueba ciega final.
- Metas: reglas solas ≥75 % de conversacionales del banco; con MiniLM real ≥90 %; 0 falsos positivos siempre.
- Bancos y golden master sin cambios de resultado.
- Comando de pruebas: `.venv\Scripts\python.exe -X utf8 -m unittest <módulo>`.
- Tras editar código: `graphify update .`.

## Review Focus

1. Respuesta corta a contrapregunta («ninguna», «sí», «la primera», «gracias» con `_pending_*` activo) → flujo normal, nunca portero. Test en Task 3.
2. Seguimiento corto sin datos («¿y en octubre?», «y por servicio», «el anterior») → no interceptado. Test en Task 1 (banco).
3. Saludo + pregunta («hola, ¿cuántas cirugías hubo?», «buenas, ocupación») → flujo normal. Test en Task 1.
4. «gracias» entre una pregunta de datos y «¿y en octubre?» → el seguimiento sigue funcionando. Test en Task 3.
5. Catálogo vacío o sin router / sin MiniLM → respuesta genérica de capacidades y solo reglas, sin excepción. Test en Tasks 2 y 3.

---

## File Structure

| Archivo | Responsabilidad |
|---|---|
| `src/chatbot/portero.py` (nuevo) | Clasificación (reglas, guardas, similitud) y textos de respuesta. Puro: no conoce el motor. |
| `tests/portero/banco_portero.json` (nuevo) | ~60 conversacionales + ~60 preguntas reales cortas/ambiguas, etiquetados. |
| `tests/portero/test_portero.py` (nuevo) | Unitarias del módulo + banco + barrido ciego de bancos reales (solo reglas). |
| `tests/portero/test_portero_minilm.py` (nuevo) | Medición con MiniLM real (skip si no está). |
| `tests/portero/test_motor_portero.py` (nuevo) | Integración con `QueryEngine` vía `tests.sim.harness`. |
| `src/chatbot/query_engine.py` | Conexión en `process()`. |
| `app.py` | Mostrar ruta `conversacion` como texto simple. |
| `src/feedback/registro.py` | `conversacion` sin modo estricto. |

---

### Task 1: Clasificador por reglas, guardas y banco

**Files:**
- Create: `src/chatbot/portero.py`, `tests/portero/__init__.py`, `tests/portero/banco_portero.json`, `tests/portero/test_portero.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Clasificacion: tipo: str; subtipo: str; confianza: float; motivo: str` — `tipo` ∈ {`"charla"`, `"identidad"`, `"capacidades"`}; `subtipo` ∈ {`"saludo"`, `"agradecimiento"`, `"despedida"`, `"estado"`, `"identidad"`, `"capacidades"`}; `motivo` ∈ {`"regla"`, `"similitud"`}.
  - `def clasificar(texto: str, vocabulario_dominio: frozenset[str] = frozenset(), similitud: "SimilitudPortero | None" = None) -> Clasificacion | None`
  - `def bloqueado_por_guardas(texto: str, vocabulario_dominio: frozenset[str]) -> str | None` — devuelve el motivo del bloqueo (`"numero"`, `"periodo"`, `"dominio"`, `"largo"`) o `None`.
  - `def normalizar(texto: str) -> str` — minúsculas, sin tildes, sin signos, espacios colapsados.

**Formato del banco** (`banco_portero.json`): `{"version": 1, "casos": [{"id": "C01", "texto": "hola", "esperado": "charla/saludo"}, {"id": "D01", "texto": "¿y en octubre?", "esperado": null}, ...]}`. `esperado` es `"tipo/subtipo"` o `null` (debe pasar al flujo normal). Incluir: variantes de chat («q tal», «buenas», «grax», «ok gracias», «holaa», «chao», «nos vemos»), tipeos, con y sin signos; en los `null`: seguimientos cortos, respuestas a contrapregunta («ninguna», «sí», «la primera», «la 2»), saludo + pregunta, preguntas de una palabra del dominio («cirugías», «ocupación»), «ayuda con las cirugías».

- [ ] **Step 1: Escribir pruebas que fallan** en `tests/portero/test_portero.py`:
  - `test_saludos_basicos`: `clasificar("hola").subtipo == "saludo"`, `clasificar("¿Cómo estás hoy?").subtipo == "estado"`, `clasificar("gracias").subtipo == "agradecimiento"`, `clasificar("¿quién eres?").tipo == "identidad"`, `clasificar("¿qué puedes hacer?").tipo == "capacidades"`, `clasificar("ayuda").tipo == "capacidades"`; todos con `motivo == "regla"`.
  - `test_saludo_mas_pregunta_no_se_intercepta`: `clasificar("hola, ¿cuántas cirugías hubo en octubre?", frozenset({"cirugias"})) is None`; `bloqueado_por_guardas(...)` devuelve `"numero"`/`"periodo"`/`"dominio"` según el caso (`"hola 2025"` → `"numero"`, `"buenas, en octubre"` → `"periodo"`).
  - `test_mensaje_largo_no_se_intercepta`: texto de 9+ palabras tras quitar el saludo → `None`, guarda `"largo"`.
  - `test_banco_portero_sin_falsos_positivos`: para cada caso con `esperado is None`, `clasificar(texto, VOCAB) is None` (VOCAB = palabras del vocabulario real, ver Step 3). Mensaje de fallo lista los ids.
  - `test_banco_portero_cobertura_reglas`: aciertos (`f"{tipo}/{subtipo}" == esperado`) / conversacionales ≥ 0.75.
  - `test_barrido_bancos_reales_sin_intercepciones`: todas las `pregunta` de `banco_real`, `banco_holdout`, `banco_holdout2` y todas las `entrada` de los `turnos` de `banco_multiturno` (más `turnos_extra` si traen texto) → `clasificar(...) is None`. Holdouts/multi-turno no se usan para ajustar reglas; si fallan, se corrige la regla general, no se añade la frase.
- [ ] **Step 2: Correr** `.venv\Scripts\python.exe -X utf8 -m unittest tests.portero.test_portero` → FAIL (módulo inexistente).
- [ ] **Step 3: Implementar** `normalizar`, `bloqueado_por_guardas`, `clasificar` (sin similitud aún) en `src/chatbot/portero.py`.
  - Reglas: el mensaje normalizado, sin muletillas («oye», «por favor», «bueno»), debe ser ENTERO una frase conversacional (coincidencia completa contra las frases de `research.md` D6), no contenerla. Tipeos: distancia de edición ≤1 solo en palabras de ≥4 letras.
  - Lista de bloqueo (research D4): «como vamos», «como estamos…», «como va/esta X», «que hay de nuevo», «resumen», «novedades», «ayuda con/para X» → `None`. «listo», «ok», «si», «no», «ninguna», «dale», «perfecto» SOLOS → `None` (son respuestas a contrapregunta). «ayuda» sola → capacidades.
  - Añadir al banco (`null`): todas las frases de la lista de bloqueo y «listo», «ok», «sí», «dale», «perfecto».
  - Guardas en orden: dígitos → `"numero"`; periodos (nombres de mes, «semana», «trimestre», «año», «ayer», «mes pasado», «anterior») → `"periodo"`; cualquier token en `vocabulario_dominio` → `"dominio"`; más de 8 palabras → `"largo"`. «hoy» solo NO bloquea («¿cómo estás hoy?»).
  - Exponer `def vocabulario_dominio(project_root) -> frozenset[str]` en `portero.py`: claves de `vocabulary_for(project_root).targets` (`src/semantic/question_normalizer.py:280`; son palabras del catálogo, NO usar `.known`, que incluye prosa y palabras comunes), normalizadas, menos las palabras conversacionales y muletillas («hola», «ayuda», «gracias», «buenas», «bien», «hoy»…). Devuelve `frozenset()` si falla. `VOCAB` de las pruebas = `vocabulario_dominio(PROJECT_ROOT)`.
  - Barrido: `turnos_extra` de `banco_real` viene como `["texto: y en agosto?"]`; quitar el prefijo `texto: `.
- [ ] **Step 4: Correr** el mismo comando → PASS.
- [ ] **Step 5: Commit** `git add src/chatbot/portero.py tests/portero/` · `git commit -m "Portero: clasificador por reglas, guardas y banco"`

### Task 2: Similitud MiniLM y textos de respuesta

**Files:**
- Modify: `src/chatbot/portero.py`
- Create: `tests/portero/test_portero_minilm.py`
- Test: `tests/portero/test_portero.py`

**Interfaces:**
- Consumes: `Clasificacion`, `clasificar`, `normalizar` (Task 1).
- Produces:
  - `class SimilitudPortero: def __init__(self, modelo, umbral: float = UMBRAL, margen: float = MARGEN)`; `def mejor(self, texto: str) -> tuple[str, float, float] | None` → `(f"{tipo}/{subtipo}", sim_conversacional, sim_dominio_max)`. Vectores de `EJEMPLOS` (20–30 por subtipo) y `REFERENCIAS_DOMINIO` (preguntas de `banco_real` + `null` del banco del portero, normalizadas) calculados una vez en `__init__` con `modelo.encode(..., normalize_embeddings=True)`. Si `encode` lanza, la instancia queda inactiva (`mejor` → `None`).
  - `clasificar(..., similitud=s)`: tras reglas y guardas, y SOLO si el mensaje normalizado tiene 3–8 palabras (≤2 palabras: solo reglas; ver research D1), intercepta si `sim ≥ umbral` y `sim − max(sim_dominio) ≥ margen`; `motivo="similitud"`. Valores iniciales `UMBRAL = 0.80`, `MARGEN = 0.20` (research D2). Vectores con `normalize_embeddings=True` y producto punto.
  - Ejemplos y lista de bloqueo: `specs/001-portero-conversacional/research.md` D4 y D6.
  - `def catalogo_tableros(router) -> tuple[list[str], list[str]]` → `(datos, documentacion)`. Datos = `semantic_model` de `router.models`; documentación = nombres de `router._documentation_dashboards` (vía `getattr`, default `[]`) cuyo nombre normalizado o grupo no coincide con ningún `semantic_model`/`semantic_model_key`. Nombres en formato título, deduplicados, ordenados. Excluir los que empiezan por «DICCIONARIO». `router is None` o error → `([], [])`.
  - `def responder(c: Clasificacion, datos: list[str], documentacion: list[str]) -> str`.
- Textos (copia fija; el implementador puede pulir redacción, se mostrarán al usuario antes de cerrar):
  - saludo / estado: «¡Hola! Estoy bien y listo para ayudarte. Puedes preguntarme por los indicadores de los tableros institucionales, por ejemplo: «¿Cuántas cirugías se realizaron el mes pasado?».»
  - agradecimiento: «Con gusto. Si necesitas otro dato, aquí estoy.»
  - despedida: «¡Hasta pronto!»
  - identidad: «Soy el asistente de consulta de los tableros institucionales del Hospital Universitario de Caldas. Respondo con datos de Power BI y con la documentación de los tableros. No doy recomendaciones clínicas.»
  - capacidades: «Puedo ayudarte con:» + «**Datos** (cifras de Power BI): A, B, C…» + «**Documentación** (qué muestra cada tablero y cómo se calcula): X, Y…» + «Ejemplo: «¿Cuál es el nivel de ocupación?»». Grupo vacío no se muestra; ambos vacíos → «Puedo responder preguntas sobre los indicadores y la documentación de los tableros institucionales. Ejemplo: …».

- [ ] **Step 1: Pruebas que fallan** en `test_portero.py` con un modelo falso (`encode` devuelve vectores fijos por texto):
  - `test_similitud_intercepta_solo_sobre_umbral_y_margen` (alto y con margen → clasifica; alto sin margen → `None`; bajo → `None`).
  - `test_similitud_no_salta_guardas` («hola, cirugías» con similitud alta → `None`).
  - `test_modelo_que_falla_deja_solo_reglas` (`encode` lanza → `clasificar("hola", similitud=s).motivo == "regla"`, `clasificar("¿todo bien por allá?", similitud=s) is None`).
  - `test_catalogo_dos_grupos` (router falso: modelo «CIRUGIAS», doc «CIRUGIAS» y «TRIAGE» → `(["Cirugias"], ["Triage"])`; «DICCIONARIO X» excluido); `test_catalogo_sin_router` → `([], [])`.
  - `test_respuesta_capacidades` (contiene «**Datos**» y «**Documentación**» con nombres; grupo vacío omitido; ambos vacíos → texto genérico) y `test_respuesta_identidad_dice_no_clinico`.
- [ ] **Step 2: Correr** `tests.portero.test_portero` → FAIL.
- [ ] **Step 3: Implementar** lo de Interfaces en `portero.py`.
- [ ] **Step 4: Correr** → PASS.
- [ ] **Step 5: Calibrar con MiniLM real** en `tests/portero/test_portero_minilm.py`: `setUpClass` carga `SentenceTransformer(MODEL_NAME)` de `src.rag.retriever` con `local_files_only` si es posible; si falla → `skipTest`. Pruebas: banco del portero ≥90 % aciertos y 0 falsos positivos; `clasificar` con similitud < 50 ms de media por mensaje tras precalcular; barrido de bancos reales 0 interceptados. Ajustar `UMBRAL`/`MARGEN` mirando SOLO el banco del portero y `banco_real`; anotar en el docstring del módulo los valores y las cifras obtenidas. Luego correr el barrido ciego (holdouts, multi-turno) una sola vez.
- [ ] **Step 6: Correr** `.venv\Scripts\python.exe -X utf8 -m unittest tests.portero.test_portero tests.portero.test_portero_minilm` → PASS (o skip del segundo con motivo).
- [ ] **Step 7: Commit** `"Portero: similitud MiniLM calibrada y respuestas desde el catálogo"`

### Task 3: Conexión al motor, app y registro

**Files:**
- Modify: `src/chatbot/query_engine.py` (`process()`, ~L6576), `app.py` (`get_display_answer` ~L271 y el bloque de detalles ~L670), `src/feedback/registro.py` (`_respuesta`, ~L253)
- Create: `tests/portero/test_motor_portero.py`
- Test: `tests/feedback/test_registro.py`

**Interfaces:**
- Consumes: `clasificar`, `SimilitudPortero`, `catalogo_tableros`, `responder`, `vocabulario_dominio` (Tasks 1–2).
- Produces: resultado `{"status": "success", "route": "conversacion", "answer": str, "conversation_kind": "tipo/subtipo", "question": message}`.

Reglas de la conexión:
- Solo en turno de primer nivel (`top_level`) y si NO hay `_pending_query_plan`, `_pending_dashboard_clarification`, `_pending_master_metric`, `conversation_manager.state.awaiting_clarification` ni `_applying_deferred`. La comprobación se hace ANTES de borrar `_deferred_context_message`.
- Clasifica el texto normalizado. `SimilitudPortero` y el vocabulario se construyen perezosamente una vez por motor (`rag_answer_engine.retriever.model`; si no existe, `similitud=None`). Cualquier excepción del portero → flujo normal (nunca tumba el turno).
- Dentro de `_traced("question", …)` con `self._think("Mensaje conversacional", f"{tipo}/{subtipo} ({motivo}): respondido sin buscar en la documentación ni en Power BI")`.
- No llama `_record_turn` ni cambia `_last_success`.
- `app.py`: `get_display_answer` devuelve `result["answer"]` para `route == "conversacion"`; sin bloque de informe/métrica.
- `registro.py`: `estricto=result.get("route") not in ("rag", "conversacion")`.

- [ ] **Step 1: Pruebas que fallan** en `test_motor_portero.py` (con `tests.sim.harness`, sin Power BI real):
  - `test_hola_responde_sin_buscar`: ruta `conversacion`, el retriever falso no recibió `search*`, ningún DAX ejecutado, el razonamiento contiene «Mensaje conversacional».
  - `test_que_puedes_hacer_lista_tableros_del_catalogo` (nombres del registro de fixtures en «**Datos**»).
  - `test_no_actua_con_contrapregunta_pendiente`: pregunta ambigua que deja contrapregunta → «ninguna» y «gracias» no dan ruta `conversacion`.
  - `test_gracias_no_rompe_seguimiento`: pregunta de datos → «gracias» → «¿y en octubre?»: el tercer turno es seguimiento con el mismo indicador que el primero.
  - `test_saludo_mas_pregunta_va_a_datos`.
  - `test_portero_que_lanza_no_tumba_el_turno` (parchear `clasificar` para lanzar → flujo normal).
  - `test_sin_rag_answer_engine_usa_solo_reglas`.
  - En `tests/feedback/test_registro.py`: `test_ruta_conversacion_conserva_lista` (respuesta con viñetas de tableros se guarda completa).
- [ ] **Step 2: Correr** `.venv\Scripts\python.exe -X utf8 -m unittest tests.portero.test_motor_portero tests.feedback.test_registro` → FAIL.
- [ ] **Step 3: Implementar** la conexión, `app.py` y `registro.py` según las reglas.
- [ ] **Step 4: Correr** lo mismo → PASS; luego regresión: `.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -t .` (excluyendo lo que requiera Power BI/servicios, como en la suite actual) y `tests.sim.test_smoke` → sin fallos nuevos.
- [ ] **Step 5: Commit** `"Portero conectado al motor: ruta conversacion, app y registro"`; `graphify update .`.

### Task 4: Verificación final

- [ ] **Step 1:** Simulador (`tests.sim.harness`) con «¿Cómo estás hoy?», «hola», «gracias», «¿quién eres?», «¿qué puedes hacer?»: ruta `conversacion`, 0 DAX; el saludo aparece en `export_conversation_markdown` (`src/chatbot/conversation_export.py`) con los mensajes de la app. Mostrar las 5 respuestas al usuario.
- [ ] **Step 2:** Bancos reales (`tests/real/correr_todo.py`) — los corre el usuario o se corren con su permiso (consultan Power BI en solo lectura): mismos porcentajes que antes (96/80/22, multi-turno).
- [ ] **Step 3:** Golden master `python -m tests.resolution.test_golden` (~1 h) — a decisión del usuario.
- [ ] **Step 4:** `graphify update .` y commit final si hubo ajustes.
