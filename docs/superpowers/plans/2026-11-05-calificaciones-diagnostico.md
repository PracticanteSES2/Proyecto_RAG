# Calificaciones en modo diagnóstico — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans. Los pasos usan casillas `- [ ]`.

**Goal:** En «Modo diagnóstico», calificar cada respuesta (buena/mala + qué se esperaba) y guardar el turno completo en un JSONL para entrenar después el enrutador y ajustar las respuestas.

**Architecture:** `src/feedback/registro.py` (snapshot saneado, registro y escritura), `lector.py` (lectura, última línea por turno), `panel.py` (UI Streamlit). `app.py` guarda el snapshot en cada mensaje del asistente y llama al panel solo con `debug_mode`.

**Tech Stack:** Python, Streamlit 1.64 (`st.feedback`, `st.text_area`, `AppTest`), unittest, JSONL.

**Spec:** docs/superpowers/specs/2026-11-05-calificaciones-diagnostico-design.md

## Global Constraints
- Power BI y BD de producción solo lectura; **cero consultas nuevas**.
- Nada de filas de pacientes en el log: respuesta sin líneas que empiecen por `|`, recortada a 1500 caracteres; se descartan claves `rows`, `data`, `table`, `dataframe`, y los chunks se guardan sin texto.
- Sin dependencias nuevas. Sin nombre de evaluador. Ruta por defecto `data/feedback/calificaciones.jsonl`, sobreescribible con `FEEDBACK_DIR`.
- Un fallo de guardado nunca rompe el chat. Sin `debug_mode` el chat queda idéntico.
- Pruebas con `python -m unittest tests.feedback.<modulo>` (estilo del proyecto).

## Review Focus
- «Mala» sin comentario → rechazado (`ValueError`), nada se escribe.
- Respuesta con tabla de pacientes → el log no contiene ninguna línea `|…|`.
- Carpeta del log inexistente → se crea; línea corrupta en el archivo → se omite al leer.
- «Nueva conversación» reinicia los índices de mensajes → `id_sesion` debe renovarse, o los `id_turno` chocan.
- Mensajes sin `snapshot` (saludo inicial, mensajes del usuario) → no muestran panel.
- Escrituras concurrentes (varias pestañas) → una línea válida por escritura.

---

### Task 1: Registro y lector

**Files:** Create `src/feedback/__init__.py`, `src/feedback/registro.py`, `src/feedback/lector.py`, `tests/feedback/__init__.py`, `tests/feedback/test_registro.py`.

**Interfaces — Produces:**
- `ruta_log() -> Path`
- `snapshot_turno(result: dict, respuesta: str, pregunta: str, via: str, opciones: list[str]) -> dict` — campos: `pregunta, via, estado, ruta, etapa, informe, tablero, modelo_semantico, metrica, plan_consulta, contexto_fuentes, modo_sintesis, fuentes[{id, coleccion, tablero, tipo_chunk, puntaje}], opciones_contrapregunta, respuesta, error, fecha_turno`.
- `construir_registro(snapshot: dict, historial: list[dict], calificacion: str, esperado: str, id_sesion: str, indice: int) -> dict` — añade `version=1, id_turno=f"{id_sesion}:{indice}", id_sesion, indice_turno, fecha_calificacion, commit_codigo, historial` (últimos 6 `{rol, texto}`), `calificacion` ∈ {"buena","mala"}, `esperado`. `ValueError` si la calificación es otra o si es «mala» con `esperado` vacío/solo espacios.
- `guardar(registro: dict, ruta: Path | None = None) -> None` — crea la carpeta, candado de hilo, una sola `write` de `json.dumps(..., ensure_ascii=False) + "\n"`.
- `cargar_calificaciones(ruta: Path | None = None) -> list[dict]` — última línea por `id_turno`, omite líneas corruptas, `[]` si no existe el archivo.

- [ ] **Step 1: Pruebas que fallan** en `tests/feedback/test_registro.py` (con carpeta temporal vía `FEEDBACK_DIR`): `test_snapshot_sin_filas_de_tabla` (respuesta `"Total 5\n| paciente | x |\n| Ana | 1 |"` → no contiene `"|"`), `test_snapshot_recorta_a_1500`, `test_snapshot_descarta_claves_de_filas_y_texto_de_chunks`, `test_mala_sin_esperado_rechazada` (`ValueError`, y `guardar` no se llama), `test_calificacion_invalida_rechazada`, `test_historial_ultimos_6`, `test_guardar_crea_carpeta_y_lector_devuelve_ultima` (dos registros mismo `id_turno`, buena→mala; el lector devuelve 1 con «mala»), `test_lector_omite_linea_corrupta`, `test_escritura_concurrente_20_hilos_20_lineas_validas`.
- [ ] **Step 2:** `python -m unittest tests.feedback.test_registro` → FALLA (módulo inexistente).
- [ ] **Step 3: Implementar** `registro.py` y `lector.py` con las firmas de arriba. `commit_codigo`: `git rev-parse --short HEAD` en la raíz del proyecto, con `functools.lru_cache`, `""` si falla. Quitar líneas de tabla con `line.lstrip().startswith("|")`.
- [ ] **Step 4:** misma orden → PASA.
- [ ] **Step 5:** `graphify update .`

### Task 2: Panel y conexión con `app.py`

**Files:** Create `src/feedback/panel.py`, `tests/feedback/test_panel.py`; Modify `app.py` (`execute_turn` ~l.588-760, bucle de historial ~l.827, botón «Nueva conversación» ~l.785-815).

**Interfaces — Consumes:** `snapshot_turno`, `construir_registro`, `guardar` (Task 1).
**Produces:** `mostrar_calificacion(indice: int, mensajes: list[dict]) -> None` — usa `mensajes[indice]["snapshot"]`; `id_sesion` en `st.session_state["id_sesion"]` (se crea con `uuid4().hex[:12]` si falta). Muestra `st.feedback("thumbs", key=f"cal_{id_sesion}_{indice}")`; con 👎 muestra `st.text_area("¿Qué esperabas que respondiera? (no incluyas datos de pacientes)")` y `st.button("Guardar")`; con 👍 guarda al instante y muestra «Guardado ✔». Un error al guardar se muestra con `st.warning` y no se propaga.

- [ ] **Step 1: Pruebas que fallan** en `tests/feedback/test_panel.py` con `streamlit.testing.v1.AppTest.from_function` (script mínimo que llama `mostrar_calificacion(1, mensajes)`; `FEEDBACK_DIR` temporal): `test_buena_guarda_una_linea`, `test_mala_sin_comentario_no_guarda_y_avisa`, `test_mala_con_comentario_guarda_esperado`, `test_mensaje_sin_snapshot_no_muestra_panel`. Más una prueba con la app real (patrón de `tests/export/test_export.py` y `tests/realistic/run_app.py`): `test_app_panel_solo_con_modo_diagnostico`.
- [ ] **Step 2:** `python -m unittest tests.feedback.test_panel` → FALLA.
- [ ] **Step 3: Implementar** `panel.py`. En `app.py`: (a) al añadir el mensaje del asistente en `execute_turn`, incluir `"snapshot": snapshot_turno(result, answer, user_text, via, [b["label"] for b in buttons or []])` en un `try/except` (si falla, sin snapshot); (b) en el bucle de historial, tras `render_reasoning(...)`, `if debug_mode and message.get("snapshot"): mostrar_calificacion(message_index, st.session_state.messages)`; (c) lo mismo para el turno en vivo, justo después de añadir el mensaje, con `len(st.session_state.messages) - 1`; (d) en «Nueva conversación» borrar `st.session_state["id_sesion"]` junto con `messages = []`.
- [ ] **Step 4:** `python -m unittest tests.feedback.test_panel tests.feedback.test_registro tests.export.test_export` → PASA (export sin regresión).
- [ ] **Step 5:** `graphify update .`

### Task 3: Verificación (sin commit hasta aprobación)

- [ ] **Step 1:** Ejecutar las suites relacionadas (`tests.feedback.*`, `tests.export.*`) y mostrar el resultado real.
- [ ] **Step 2:** Levantar la app temporalmente, capturar el panel con Edge/Playwright (entorno aparte del proyecto), apagar la app y comprobar el puerto libre.
- [ ] **Step 3:** Mostrar capturas y un ejemplo de línea del JSONL (con datos de prueba, sin pacientes) al usuario; el commit solo cuando lo apruebe.
