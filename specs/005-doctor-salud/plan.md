# Implementation Plan: Doctor de salud del proyecto

**Branch**: `agente/doctor` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

## Summary

Orquestador propio `tools/doctor/` con la librería estándar (`ast`, `tomllib`, `subprocess`
para `git`) que aplica reglas del proyecto en 7 categorías, calcula un puntaje 0-100 y
compara con una línea base versionada (trinquete). Integra `ruff` y `vulture` solo si están
instalados, como información que no cambia el puntaje.

## Investigación (resumen)

- **react-doctor** (millionco): `npx react-doctor .` escanea un proyecto React (lint, código
  muerto con knip, seguridad, rendimiento), da un puntaje 0-100 ponderado por severidad
  (≥75 bien, 50-74 necesita trabajo, <50 crítico), `--diff` para solo cambios y
  `--fail-on` para CI.
- **Equivalentes Python**: ruff (lint rápido, F401/F841/E722/T201), radon/xenon
  (complejidad ciclomática y umbrales), vulture (código muerto), deptry (dependencias
  declaradas vs usadas), import-linter (contratos de capas), pylint duplicate-code / jscpd
  (clones), wily (historial de métricas).
- **Decisión**: ninguna cubre las reglas propias (lista blanca de la raíz, capas de `src`,
  utilidades repetidas, pruebas huérfanas, mojibake) ni da un puntaje único con trinquete por
  huellas. Se implementan las reglas con `ast` (complejidad tipo McCabe, clones tipo 1 y 2,
  grafo de importaciones con Tarjan para ciclos) y se dejan ruff/vulture como externas
  opcionales (`requirements-dev.txt`). El puntaje no depende de lo instalado.

## Cambio de rumbo (2026-11-10): dos perfiles

El stack pasa a backend FastAPI (`backend/`, importa el motor de `src/`) + frontend Next.js
App Router con TypeScript (`frontend/`) + Redis. El doctor queda como orquestador con dos
perfiles:

- **backend** (`motor.analizar`): las 7 categorías de arriba + `fastapi`
  (`reglas/fastapi.py`). El legado Streamlit se mide (archivos y líneas) y su crecimiento
  respecto de la línea base es `legado_crece` (alta).
- **frontend** (`frontend.py`): reglas propias por regex (estructura, tipos, arquitectura,
  higiene) que no necesitan Node + `tsc --noEmit`, ESLint (`--format json`) y react-doctor
  0.9.22 (`--json --no-score --blocking none -y --no-supply-chain`; local en
  `node_modules/.bin` o `npx`). Su JSON no está documentado: lector tolerante. Categoría sin
  herramienta → omitida con motivo, fuera del puntaje y del trinquete.
- **Global** = media ponderada de perfiles (backend 60 / frontend 40); línea base v2 con
  secciones por perfil.

## Technical Context

**Language/Version**: Python 3.14 (sin dependencias nuevas en tiempo de ejecución)
**Primary Dependencies**: librería estándar; opcional ruff, vulture
**Testing**: `unittest` con mini-repos en `tempfile.TemporaryDirectory`
**Performance Goals**: < 30 s sobre el repo (≈280 archivos .py; parseo ≈5 s)
**Constraints**: solo lectura; sin red; sin `.env`

## Diseño

```
tools/doctor/
  __main__.py      → cli.main()
  cli.py           → argumentos, informe consola/JSON/Markdown, verificar, actualizar
  config.py        → carga reglas.toml (con valores por defecto)
  modelo.py        → Hallazgo, Informe
  repo.py          → listado de archivos (git o disco), AST cacheado, módulos, importaciones
  puntaje.py       → puntaje por categoría y global
  linea_base.py    → guardar/comparar (trinquete)
  externas.py      → ruff/vulture opcionales
  reglas/          → estructura, tamano, duplicacion, muerto, capas, pruebas, higiene
  reglas.toml      → configuración
  linea_base.json  → listón actual
```

**Puntaje**: por categoría, `P = Σ_(regla,severidad) peso_sev · √n`;
`puntaje = 100 · E / (E + P)` con `E` = `escala` de la categoría. La raíz cuadrada hace que
arreglar una regla entera cuente más que bajar una ocurrencia, pero cualquier hallazgo nuevo
baja el puntaje (el trinquete lo detecta). Global = media ponderada por `peso`.

**Trinquete**: la línea base guarda puntajes (4 decimales) y el conteo de huellas por
severidad. `--verificar` falla si `actual < base − tolerancia` en global o en alguna
categoría, o si una huella alta aparece más veces que en la base.

## Constitution Check

Sin constitución específica del proyecto que aplique; se respetan las reglas de CLAUDE.md
(spec-kit, TDD, graphify update tras cambios).

## Project Structure

```
specs/005-doctor-salud/   spec.md, plan.md, tasks.md
tools/doctor/             (arriba)
tests/doctor/             test_reglas.py, test_cli.py, test_repo.py
docs/calidad/doctor.md    guía de uso
.claude/agents/revisor-estructura.md
requirements-dev.txt
```
