# Calificaciones en modo diagnóstico — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans. Los pasos usan casillas `- [ ]`.

**Goal:** En «Modo diagnóstico», calificar cada respuesta (buena/mala + qué se esperaba) y guardar el turno completo en un JSONL para entrenar después el enrutador y ajustar las respuestas.

**Architecture:** `src/feedback/registro.py` (snapshot saneado, registro y escritura), `lector.py` (lectura, última línea por turno), `panel.py` (UI Streamlit). `app.py` guarda el snapshot en cada mensaje del asistente y llama al panel solo con `debug_mode`.

**Tech Stack:** Python, Streamlit 1.64 (`st.feedback`, `st.text_area`, `AppTest`), unittest, JSONL.

**Spec:** docs/superpowers/specs/2026-11-05-calificaciones-diagnostico-design.md

## Global Constraints
- Power BI y BD de producción solo lectura; **cero consultas nuevas**.
- Nada de filas de pacientes en el log. **LISTA BLANCA** (no lista negra): el snapshot copia SOLO los campos del registro v1. Nunca se copian `rows`, `value`, `detail`, `details`, `powerbi`, `dax`, `contexts`, `reasoning`, `domain`, ni `sources[*].text`. Filtros: solo `{tipo, tabla, columna}` y cantidad de valores (sin valores). Textos libres (`pregunta`, `historial[*].texto`, `esperado`, `respuesta`, `error`): secuencias de 6+ dígitos → `[NUM]`; líneas que empiezan por `|` fuera; `respuesta` ≤1500 caracteres (si `ruta=="powerbi"` y `result_type` es tabla/detalle: solo la primera línea, ≤400); `error` ≤200.
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
- `snapshot_turno(result: dict, respuesta: str, pregunta: str, via: str, opciones: list[str]) -> dict` — campos (lista blanca): `pregunta, pregunta_reescrita, via, estado, ruta, etapa, informe, tablero, modelo_semantico, metrica, plan_consulta` (subconjunto: `metric, report, semantic_model, group_by, mode` y filtros `{tipo, tabla, columna, n_valores}`), `contexto_fuentes` (`semantic_model`, `routing_strength`, `reason`, `status` y `candidates[{id, modelo, tablero, score}]` con score a 4 decimales), `modo_sintesis, retrieval_mode, not_found_reason, fuentes[{id, coleccion, tablero, tipo_chunk, puntaje}], opciones_contrapregunta, respuesta, error, fecha_turno, tablero_esperado=None` (reservado para una fase 2; sin UI).
- `construir_registro(snapshot: dict, historial: list[dict], calificacion: str, esperado: str, id_sesion: str, indice: int) -> dict` — añade `version=1, id_turno=f"{id_sesion}:{indice}", id_sesion, fecha_calificacion, commit_codigo, historial` (últimos 6 `{rol, texto}`, saneados), `calificacion` ∈ {"buena","mala"}, `esperado` (saneado). No hay `indice_turno`. `ValueError` si la calificación es otra o si es «mala» con `esperado` vacío/solo espacios.
- `guardar(registro: dict, ruta: Path | None = None) -> None` — crea la carpeta; `threading.Lock` + candado ENTRE PROCESOS (`msvcrt.locking(fd, LK_NBLCK, 1)` sobre `<log>.lock`, con reintento corto) + `open(ruta, "ab")` y UNA sola `write` de bytes UTF-8 de `json.dumps(..., ensure_ascii=False) + "\n"` (sin `\r\n`) + `flush`; reintenta 3 veces (50–100 ms) ante `PermissionError`; si sigue fallando, lanza la excepción (el panel la captura). Medido por el investigador: sin candado entre procesos se pierde ~3–7 % de líneas en Windows.
- `cargar_calificaciones(ruta: Path | None = None) -> list[dict]` — última línea por `id_turno`, omite líneas corruptas, `[]` si no existe el archivo.

- [ ] **Step 1: Pruebas que fallan** en `tests/feedback/test_registro.py` (con carpeta temporal vía `FEEDBACK_DIR`): `test_snapshot_sin_filas_de_tabla` (respuesta `"Total 5\n| paciente | x |\n| Ana | 1 |"` → no contiene `"|"`), `test_snapshot_recorta_a_1500`, `test_snapshot_descarta_claves_de_filas_y_texto_de_chunks`, `test_mala_sin_esperado_rechazada` (`ValueError`, y `guardar` no se llama), `test_calificacion_invalida_rechazada`, `test_historial_ultimos_6`, `test_guardar_crea_carpeta_y_lector_devuelve_ultima` (dos registros mismo `id_turno`, buena→mala; el lector devuelve 1 con «mala»), `test_lector_omite_linea_corrupta`, `test_escritura_concurrente_20_hilos_20_lineas_validas`, `test_escritura_concurrente_4_procesos_x_50_todas_validas` (multiprocessing, 200 líneas válidas), `test_lista_blanca_no_copia_dax_value_detail_ni_valores_de_filtros` (siembra `dax`, `value`, `detail.rows`, `reasoning`, `filters[].values` y comprueba que ninguno aparece en el JSON), `test_numeros_largos_se_enmascaran` (una cédula de 10 dígitos en `pregunta` y `esperado` → `[NUM]`), `test_candidates_y_pregunta_reescrita_presentes`.
- [ ] **Step 2:** `python -m unittest tests.feedback.test_registro` → FALLA (módulo inexistente).
- [ ] **Step 3: Implementar** `registro.py` y `lector.py` con las firmas de arriba. `commit_codigo`: `git rev-parse --short HEAD` en la raíz del proyecto, con `functools.lru_cache`, `""` si falla. Quitar líneas de tabla con `line.lstrip().startswith("|")`.
- [ ] **Step 4:** misma orden → PASA.
- [ ] **Step 5:** `graphify update .`

### Task 2: Panel y conexión con `app.py`

**Files:** Create `src/feedback/panel.py`, `tests/feedback/test_panel.py`; Modify `app.py` (`execute_turn` ~l.588-760, bucle de historial ~l.827, botón «Nueva conversación» ~l.785-815).

**Interfaces — Consumes:** `snapshot_turno`, `construir_registro`, `guardar` (Task 1).
**Produces:** `mostrar_calificacion(indice: int, mensajes: list[dict]) -> None` — usa `mensajes[indice]["snapshot"]`; `id_sesion` en `st.session_state["id_sesion"]` (se crea con `uuid4().hex[:12]` si falta). Muestra `st.feedback("thumbs", key=f"cal_{id_sesion}_{indice}")`; con 👎 muestra `st.text_area("¿Qué esperabas que respondiera? (no incluyas datos de pacientes)")` y `st.button("Guardar")`; con 👍 guarda al instante y muestra «Guardado ✔». Un error al guardar se muestra con `st.warning` y no se propaga.

- Hechos verificados (Streamlit 1.64): `st.feedback("thumbs")` devuelve **1 = 👍, 0 = 👎, None = limpiado** (no guardar) y repite el valor en cada rerun → guardar solo si calificación/comentario difieren de lo ya guardado (estado `st.session_state[f"guardado_{id_turno}"]`). `key` única por turno para `feedback`, `text_area` y botón (`key=f"guardar_{id_turno}"`). AppTest NO tiene `at.feedback`: usar `at.get("feedback")[i].set_value(n).run()`, `at.text_area[i].set_value(...)`, y el botón por `key`. El panel mapea `role→rol`, `content→texto` al armar el historial.
- [ ] **Step 1: Pruebas que fallan** en `tests/feedback/test_panel.py` con `streamlit.testing.v1.AppTest.from_function` (script mínimo que llama `mostrar_calificacion(1, mensajes)`; `FEEDBACK_DIR` temporal): `test_dos_reruns_con_buena_dejan_una_sola_linea`, `test_limpiar_el_pulgar_no_guarda`, `test_buena_guarda_una_linea`, `test_mala_sin_comentario_no_guarda_y_avisa`, `test_mala_con_comentario_guarda_esperado`, `test_mensaje_sin_snapshot_no_muestra_panel`. Más una prueba con la app real (patrón de `tests/export/test_export.py` y `tests/realistic/run_app.py`): `test_app_panel_solo_con_modo_diagnostico`.
- [ ] **Step 2:** `python -m unittest tests.feedback.test_panel` → FALLA.
- [ ] **Step 3: Implementar** `panel.py`. En `app.py`: (a) al añadir el mensaje del asistente en `execute_turn`, incluir `"snapshot": snapshot_turno(result, answer, user_text, via, [b["label"] for b in buttons or []])` en un `try/except` (si falla, sin snapshot); (b) en el bucle de historial, tras `render_reasoning(...)`, `if debug_mode and message.get("snapshot"): mostrar_calificacion(message_index, st.session_state.messages)`; (c) lo mismo para el turno en vivo, justo después de añadir el mensaje, con `len(st.session_state.messages) - 1`; (d) en «Nueva conversación» borrar `st.session_state["id_sesion"]` junto con `messages = []`.
- [ ] **Step 4:** `python -m unittest tests.feedback.test_panel tests.feedback.test_registro tests.export.test_export` → PASA (export sin regresión).
- [ ] **Step 5:** `graphify update .`

### Task 3: Verificación (sin commit hasta aprobación)

- [ ] **Step 1:** Ejecutar las suites relacionadas (`tests.feedback.*`, `tests.export.*`) y mostrar el resultado real.
- [ ] **Step 2:** Levantar la app temporalmente, capturar el panel con Edge/Playwright (entorno aparte del proyecto), apagar la app y comprobar el puerto libre.
- [ ] **Step 3:** Mostrar capturas y un ejemplo de línea del JSONL (con datos de prueba, sin pacientes) al usuario; el commit solo cuando lo apruebe.
