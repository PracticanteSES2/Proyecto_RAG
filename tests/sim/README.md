# Simulación offline del chatbot (`tests/sim`)

Ejecuta el `build_system()` REAL de `app.py` (HybridRetriever, PowerBIProvider, OllamaProvider, SourceModelRouter,
QueryPlanBuilder, QueryEngine, ...) contra datos y servicios falsos. No necesita Power BI, Ollama, Qdrant ni
paquetes extra.

## Qué simula

| Real | Simulado en `fakes.py` |
| --- | --- |
| Power BI (XMLA / pyadomd / `clr`) | `FakeDaxEngine` detrás del cliente ADOMD falso compartido con `tests/realistic` (`tests/common/adomd.py`): valida tablas/columnas/medidas y evalúa `ROW`, `CALCULATE`, `SUMMARIZECOLUMNS`, `TREATAS` (también pares `TREATAS({(2024, 11), ...}, AÑO, MES)`), `KEEPFILTERS`, `FILTER(ALL(col), col >= DATE(..))`, `MONTH(col) = n` / `MONTH(col) IN {..}`, `UNION(ROW(...), ...) ORDER BY` (agrupación por mes/trimestre) y `VALUES`. Registra cada DAX y marca los **type mismatch** (p. ej. columna entera `AÑO` comparada con `DATE()`). |
| Qdrant + sentence-transformers | Qdrant en memoria con embeddings hash deterministas, cargado de `fixtures/data/vector_db/qdrant/points.json` |
| Ollama | Cliente falso (`ollama_up=False` lo simula caído) |
| `dotenv` | No-op: **el `.env` nunca se abre ni se lee** |

Modelos semánticos falsos: *Atenciones Institucionales*, *Gestion Quirurgica* (valores "canned") y **Lavanderia**
(réplica del tablero real documentado; datos a nivel de fila: `SUM(Peso)` de ANTIFLUIDOS en enero 2026 = 488.3 y total
enero 2026 = 3906.4, es decir 12.5 % de participación).

El código fuente se importa de la raíz real del repo y los datos salen de `tests/sim/fixtures/` (que hace de
`PROJECT_ROOT`). Todo se deriva de `__file__`, así que funciona también en un `git worktree`.
Nunca se modifica código de `src/` ni `app.py`.

## Cómo ejecutar (desde la raíz del repo)

```bash
export PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8     # PowerShell: $env:PYTHONDONTWRITEBYTECODE=1

python -m tests.sim.run_smoke --quiet                       # todas las conversaciones, informe legible
python -m tests.sim.run_smoke --quiet --case lav_q1         # un caso (repetible o separado por comas)
python -m tests.sim.run_smoke --list                        # lista los casos
python -m tests.sim.run_smoke --quiet --mode master         # sin QueryPlan (ruta MasterMetric/Legacy)
python -m tests.sim.run_smoke --quiet --ollama-down         # o --powerbi-down

python -m tests.sim.test_smoke                              # PASS / FAIL / XFAIL / XPASS (exit != 0 si hay FAIL)
pytest tests/sim/test_smoke.py                              # también funciona si algún día se instala pytest
```

`PYTHONDONTWRITEBYTECODE=1` evita modificar los `__pycache__/*.pyc` versionados.

Regenerar fixtures (tras cambiar `build_fixtures.py`): `python -m tests.sim.build_fixtures`.

## XFAIL / XPASS

Los tests con `@xfail("motivo")` describen el comportamiento deseado que hoy falla por un bug real del proyecto.
El runner los lista aparte; si uno empieza a pasar aparece como **XPASS**: quita la marca `@xfail`.

## Cómo agregar un caso

1. Añade una entrada en `cases.py`: `"mi_caso": {"label": "...", "turns": ["pregunta", "respuesta a aclaración"]}`
   (cada caso es una conversación nueva; `app.py::reset_if_finished` se aplica tras cada turno).
2. Pruébalo: `python -m tests.sim.run_smoke --quiet --case mi_caso`.
3. Añade `def test_...` en `test_smoke.py` usando `last("mi_caso")` -> `(result, ui)`; `result["_sim"]` trae
   `dax_log`, `type_mismatch`, `warnings`, `exception`. Si el comportamiento deseado hoy falla, decóralo con `@xfail`.
4. Para otro dato falso: edita `build_fixtures.py` y regenera los fixtures.

API del arnés: `harness.build_engine(sim_root=None, ollama_up=True, powerbi_up=True)` devuelve
`(engine, conversation_manager, formatter, ollama_status, powerbi_connection, dax_log)` y
`harness.ask(engine, cm, formatter, texto)` devuelve `(result, ui)`, donde `ui` es exactamente lo que mostraría la app.

## Garantías

- Nunca toca `.env` ni el Power BI real (no hay red ni credenciales).
- No instala nada: los paquetes ausentes se sustituyen en `sys.modules`.
