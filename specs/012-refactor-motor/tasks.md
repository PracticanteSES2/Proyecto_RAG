# Tareas: Refactor del motor (ronda 1)

Leyenda: [x] hecho en esta ronda · [ ] pendiente (con dueño o motivo).

## Fase 0 — Andamiaje
- [x] T001 `pyproject.toml` con ruff (F, E, W, I, B, UP, T201; 120), sin reformatear.
- [x] T002 `README.md` de la raíz.
- [x] T003 `.specify/memory/constitution.md` con los principios reales.

## Fase 1 — Capas y raíz (sin `src/fabrica.py`, que es del agente de backend)
- [x] T010 `runtime_stats` → `src/comun/estadisticas.py` (+ `src/comun/entorno.py`); reexporte en `src/chatbot/runtime_stats.py`; `powerbi_provider` importa de `src.comun`. Prueba: `tests/comun/test_estadisticas.py`.
- [ ] T011 `src/llm/llm_gate.py` y `src/llm/gate_backends.py` → `src.comun.estadisticas` / `src.comun.entorno` (archivos del agente de LLM: cambio de una línea cada uno; quita los 2 hallazgos `capa_invertida` restantes).
- [x] T012 16 módulos de `src` usan `src.comun.rutas.RAIZ_PROYECTO` (legado `pages/` y `src/ui/estilo.py` congelados).

## Fase 3 — Utilidades canónicas
- [x] T020 `src/comun/texto.py` (`plegar`, `normalizar(conservar=)`, `llave`, `slug`, `sin_tildes`) + `tests/comun/test_texto.py` (oráculos; `TEXTO_EXHAUSTIVO=1` recorre todo).
- [x] T021 Sustituciones equivalentes (ver `plan.md` y el commit) y comentario en las variantes que difieren.
- [ ] T022 Variantes en archivos de otros agentes (sustituir cuando integren; equivalencias ya probadas):
      probadas: `query_engine._normalize_text` ≡ `normalizar`, su `plain` local ≡ `plegar` (paso 0 de `fase2.md`),
      `conversation_manager._normalize` ≡ `normalizar`; candidatas (añadir oráculo al sustituir): `progreso._normalizar`
      ≈ `sin_tildes(lower).strip()`, `grounding._fold` ≈ `sin_tildes(lower)`. No equivalentes (se quedan): `portero.normalizar` (NFKD),
      `portero_alcance.normalizar_operaciones`, `option_describer._plain` (sin `strip`), `answer_synthesizer._words`.
- [x] T023 `src/comun/json_io.py` (`leer_json`, `escribir_json`) y `src/comun/colecciones.py` (`como_lista`) + `tests/comun/test_json_io.py`.
- [x] T024 `src/comun/registro.py` (`configurar_registro`, `mensajes_de`, `consola_utf8`); `print` → `logging` en los constructores; CLIs configuran el registro.
- [ ] T025 `print` que quedan a propósito: `src/docs_md/diccionario.py` (salida del CLI `main`, que las pruebas leen por stdout: mover el CLI a `tools/` en la fase 4b) y `src/providers/powerbi_token.login` (mensaje del código de dispositivo para la persona).
- [x] T026 `except Exception: pass` de la librería: registran en `debug` o justifican.

## Fase 4 — Ciclos
- [x] T030 `ingestion ↔ docs_md` y `semantic ↔ docs_md`: `src/docs_md/indexacion.py` → `src/catalogo/indexacion.py` (partida en etapas).
- [x] T031 `semantic ↔ dax`: `validate_detail_dax` → `src/dax/validacion_detalle.py`.
- [ ] T032 `chatbot ↔ llm` (aparece solo por T011).
- [ ] T033 Resto de la fase 4: constructores (`model_catalog_builder`, `visual_catalog_builder`, `powerbi_catalog_manager`, `global_master_metric_builder`, `document_normalizer`, `semantic_merge`) a `src/catalogo/`.

## Fase 2 — Partir `query_engine.py`
- [x] T040 Guion listo: `specs/012-refactor-motor/fase2.md`.
- [ ] T041 Ejecutarlo cuando los agentes de `query_engine.py` integren.

## Verificación
- [x] T050 Mojibake de `src/semantic/resolucion/__init__.py`.
- [x] T051 Suites por área + golden master contra la foto del día.
- [x] T052 Doctor `--verificar` y `--actualizar-linea-base` (sin `--forzar`).
