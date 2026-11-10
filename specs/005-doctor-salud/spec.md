# Feature Specification: Doctor de salud del proyecto

**Feature Branch**: `agente/doctor`

**Created**: 2026-11-10

**Status**: Draft

**Input**: User description: "Algo como react-doctor (escanea el proyecto, da un puntaje de salud 0-100 con diagnósticos por categoría y accionables), pero para este proyecto Python, y un umbral de salud del que nunca se baje cuando se construye algo (trinquete). Además un agente revisor que vigile que lo nuevo se cree donde y como corresponde."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ver la salud del proyecto en un comando (Priority: P1)

El dueño del proyecto ejecuta `python -m tools.doctor` y recibe en consola un puntaje global
0-100, el puntaje de cada categoría (Estructura, Tamaño y complejidad, Duplicación, Código
muerto, Capas e importaciones, Pruebas, Higiene) y el top de problemas, cada uno con
`archivo:línea` y una sugerencia accionable.

**Why this priority**: sin diagnóstico no hay trinquete ni revisor; es el MVP.

**Independent Test**: correr el comando sobre el repo y sobre mini-repos sintéticos con
problemas conocidos; cada problema sembrado aparece en su categoría con archivo y línea.

**Acceptance Scenarios**:

1. **Given** un mini-repo con `debug.log` en la raíz, **When** se ejecuta el doctor, **Then** aparece un hallazgo de Estructura de severidad alta sobre `debug.log`.
2. **Given** dos módulos con la misma función de 8 líneas, **When** se ejecuta el doctor, **Then** aparece un hallazgo de Duplicación que apunta a ambos.
3. **Given** el repo real, **When** se ejecuta el doctor, **Then** termina en menos de 30 s.

### User Story 2 - Trinquete: nunca bajar el listón (Priority: P1)

Antes de integrar un cambio se ejecuta `python -m tools.doctor --verificar`; compara con
`tools/doctor/linea_base.json` y sale con código ≠0 si el puntaje global o el de alguna
categoría baja, o si aparece un hallazgo nuevo de severidad alta. Los hallazgos viejos se
toleran. Cuando el puntaje sube, `--actualizar-linea-base` sube el listón.

**Why this priority**: es lo que pidió el usuario: un umbral del que nunca se baje.

**Independent Test**: mini-repo con línea base; añadir un `except:` desnudo hace fallar
`--verificar`; quitar un problema lo deja pasar y sugiere actualizar la línea base.

**Acceptance Scenarios**:

1. **Given** una línea base del estado actual, **When** no cambia nada, **Then** `--verificar` sale con 0.
2. **Given** una línea base, **When** se añade un archivo `notas.zip` versionado, **Then** `--verificar` sale con 1 y nombra el hallazgo nuevo.
3. **Given** una mejora, **When** se ejecuta `--actualizar-linea-base`, **Then** la línea base guarda los puntajes nuevos y `--verificar` sigue en 0.

### User Story 3 - Agente revisor de estructura (Priority: P2)

Un subagente de Claude Code (`.claude/agents/revisor-estructura.md`) revisa un diff contra
`docs/ARQUITECTURA.md` y el doctor, y bloquea si algo se crea fuera de lugar, duplica una
utilidad existente o baja el puntaje.

**Independent Test**: invocar el agente sobre un diff que crea `src/nuevo/util.py` con una
copia de una función existente; el veredicto es BLOQUEAR con la referencia a la original.

### Edge Cases

- Sin git disponible: el doctor recorre el disco respetando las exclusiones.
- Herramientas externas (ruff, vulture) ausentes: se omiten sin error; si están, su salida es informativa y no altera el puntaje (el puntaje no depende de qué haya instalado).
- Archivos con sintaxis inválida: se reportan como hallazgo alto y no detienen el análisis.
- El puntaje no depende de la fecha (la antigüedad de un TODO solo se informa).
- Archivos movidos de carpeta: sus hallazgos aparecen como nuevos (decisión consciente; se revisan y se actualiza la línea base).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El doctor MUST solo leer el repo; nunca lo modifica, salvo `linea_base.json` (con `--actualizar-linea-base`) y el archivo de `--md`.
- **FR-002**: MUST cubrir 7 categorías con peso configurable y puntaje 0-100 cada una; el global es la media ponderada.
- **FR-003**: Cada hallazgo MUST traer regla, categoría, severidad (alta/media/baja), archivo, línea, mensaje, sugerencia y una huella estable que no depende del número de línea.
- **FR-004**: La configuración (lista blanca de la raíz, capas, umbrales, exclusiones, utilidades canónicas) MUST vivir en `tools/doctor/reglas.toml`.
- **FR-005**: CLI: informe de consola, `--json`, `--md <ruta>`, `--verificar`, `--actualizar-linea-base`, `--cambios <ref>` (solo archivos cambiados), `--todo`.
- **FR-006**: `--verificar` MUST fallar (código 1) si baja el global o alguna categoría más allá de `tolerancia`, o si hay hallazgos nuevos de severidad alta respecto de la línea base.
- **FR-007**: Herramientas externas opcionales MUST no romper si faltan ni cambiar el puntaje.
- **FR-008**: Tiempo de ejecución en el repo MUST ser < 30 s.
- **FR-009** (cambio de rumbo 2026-11-10: Streamlit → FastAPI + Next.js + Redis): el doctor MUST tener dos perfiles, `backend` (Python: `src/`, `backend/`, `tools/`, `tests/`) y `frontend` (`frontend/`, Next.js App Router + TypeScript). Sin argumento corre ambos y da puntaje global + por perfil + por categoría.
- **FR-010**: Perfil backend MUST incluir reglas FastAPI: routers en `backend/app/api/v1`, `response_model`/esquemas pydantic en vez de dicts sueltos, nada de lógica de negocio en routers, nada bloqueante en `async def`, configuración con pydantic-settings y no `os.getenv` disperso.
- **FR-011**: Perfil frontend MUST envolver react-doctor (CLI `--json --no-score`), `tsc --noEmit` y ESLint, más reglas propias (sin `any`, `fetch` solo en `lib/api`, colores hex solo en tokens, tamaño de componentes). Si no existe `frontend/` o no hay Node, se salta con aviso claro; las categorías de herramientas ausentes se omiten y no puntúan.
- **FR-012**: La línea base MUST guardar backend y frontend por separado; el trinquete compara cada perfil y categoría medidos.
- **FR-013**: `app.py`, `pages/`, `.streamlit/` y `src/ui/` son LEGADO: se toleran, pero si crecen respecto de la línea base es un hallazgo alto (`legado_crece`).
- **FR-014**: Capas: `backend/app → src → providers`; `src` nunca importa `backend`, `tools` ni `tests`.
- **FR-015** (docs/ARQUITECTURA.md §12): `reglas.toml` MUST usar los valores de §12 (`src/comun` como capa base, `canonico = "src/comun/rutas.py"` para la raíz del proyecto, umbrales de §7) y el doctor MUST leer sus extensiones: `excepto` en importaciones prohibidas (p. ej. `tools.manual → tests`), destinos externos (`fastapi`, `redis`, `streamlit`), `carpetas_ignoradas` (lo que git no ignora), `nombres_prohibidos`, salidas fuera de `var/` y la arquitectura del frontend (`fetch_solo_en`, `prohibidas` entre carpetas, `generado_no_editable`, tamaño de archivos TS).

### Key Entities

- **Hallazgo**: regla, categoría, severidad, archivo, línea, mensaje, sugerencia, huella.
- **Informe**: puntajes por categoría, global, hallazgos, externos, métricas.
- **Línea base**: puntajes y conteo de huellas por severidad.

## Success Criteria *(mandatory)*

- **SC-001**: Cada regla tiene al menos una prueba con mini-repo sintético que la dispara y otra que no.
- **SC-002**: `--verificar` sobre el repo pasa en la rama con la línea base generada.
- **SC-003**: Ejecución < 30 s en el repo.

## Assumptions

- La arquitectura objetivo la define otro agente en `docs/ARQUITECTURA.md`; `reglas.toml` arranca con valores tomados de la estructura actual y se ajustará.
- Las pruebas usan `unittest` (convención del proyecto).
