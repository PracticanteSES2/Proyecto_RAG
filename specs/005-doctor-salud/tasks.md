---
description: "Tareas del doctor de salud del proyecto"
---

# Tasks: Doctor de salud del proyecto

**Input**: `specs/005-doctor-salud/` (spec, plan)

**Tests**: obligatorios (TDD). **Comando**: `.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests/doctor -t .`

## Phase 1: Setup

- [x] T001 Crear `tools/doctor/` (paquete) y `tests/doctor/__init__.py`
- [x] T002 `tools/doctor/reglas.toml` con valores iniciales de la estructura actual

## Phase 2: Foundational

- [x] T003 Pruebas que fallan: `repo` lista archivos sin git respetando exclusiones; `config` carga TOML con valores por defecto
- [x] T004 Implementar `modelo.py`, `config.py`, `repo.py`, `puntaje.py`

## Phase 3: US1 — Diagnóstico (P1) 🎯 MVP

- [x] T005 [US1] Pruebas que fallan por regla con mini-repos: estructura (raíz, temporales, carpetas sin dueño), tamaño (archivo, función, complejidad), duplicación (tipo 1, tipo 2, utilidades), muerto (módulo, función, import), capas (prohibidas, invertidas, ciclos, rotas), pruebas (sin pruebas, huérfanas, patch roto), higiene (print, except, TODO, secreto, ruta de usuario, BOM, mojibake)
- [x] T006 [US1] Implementar `reglas/*.py`
- [x] T007 [US1] CLI: consola, `--json`, `--md`, `--todo`, `--cambios`
- [x] T008 [US1] `externas.py` (ruff/vulture opcionales, informativas)

## Phase 4: US2 — Trinquete (P1)

- [x] T009 [US2] Pruebas que fallan: verificar pasa sin cambios, falla con hallazgo alto nuevo, falla si baja una categoría, pasa tras actualizar
- [x] T010 [US2] Implementar `linea_base.py`, `--verificar`, `--actualizar-linea-base`
- [x] T011 [US2] Generar `tools/doctor/linea_base.json`; prueba `tests/doctor/test_repo.py` que corre `--verificar` sobre el repo

## Phase 5: US3 — Revisor (P2)

- [x] T012 [US3] `.claude/agents/revisor-estructura.md`; `.gitignore` versiona solo `/.claude/agents/`
- [x] T013 [US3] `docs/calidad/doctor.md` (qué mide, cómo leerlo, subir el listón, hook pre-commit opcional)

## Phase 5b: Cambio de rumbo — perfiles backend/frontend

- [x] T015 Pruebas `tests/doctor/test_fastapi.py` (routers en api/v1, response_model, dict suelto, lógica en router, router que importa el motor, bloqueante en async, getenv disperso, settings sin pydantic, src→backend prohibido, reexportaciones)
- [x] T016 `tools/doctor/reglas/fastapi.py`; capas backend en `reglas.toml`; lista blanca con `backend/`, `frontend/`, `infra/`
- [x] T017 Pruebas `tests/doctor/test_frontend.py` (omisión sin frontend/ o sin Node, any/ts-ignore, fetch fuera de lib/api, hex fuera de tokens, componente grande, higiene, exclusiones, lectores de tsc/ESLint/react-doctor)
- [x] T018 `tools/doctor/frontend.py` (reglas propias + tsc/ESLint/react-doctor)
- [x] T019 Línea base v2 por perfil, legado que no crece, `--estricto`, `--forzar`; pruebas en `test_cli.py`
- [x] T020 Agentes `.claude/agents/doctor-backend.md` y `doctor-frontend.md`; revisor de ambos stacks

## Phase 6: Polish

- [x] T014 `requirements-dev.txt`; medir tiempo (< 30 s); `graphify update .` (si el CLI está instalado)
