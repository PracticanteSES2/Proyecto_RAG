# Plan: Refactor del motor (fases 0, 1, 3 y 4)

**Spec**: `specs/012-refactor-motor/spec.md` · **Guía**: `docs/ARQUITECTURA.md` §10 · **Constitución**: `.specify/memory/constitution.md`

## Enfoque

Refactor sin cambio de comportamiento, un commit por paso. Antes de cada sustitución, una prueba de
equivalencia con la implementación vieja copiada como **oráculo**; al final, golden master contra una foto
tomada el mismo día sobre `desarrollo` (worktree aparte, `SIM_CACHE_DIR` propio).

## Estructura resultante

```
src/comun/
  rutas.py          (ya existía) raíz, data/, var/
  entorno.py        env_int, env_float
  estadisticas.py   estado de ejecución (antes src/chatbot/runtime_stats.py, que queda como reexporte)
  texto.py          plegar, normalizar(conservar=), llave, slug, sin_tildes
  json_io.py        leer_json, escribir_json(atomico=, default=)
  colecciones.py    como_lista
  registro.py       configurar_registro (CLIs); la librería usa logging.getLogger(__name__)
src/catalogo/
  indexacion.py     reindexación de la documentación (antes src/docs_md/indexacion.py)
src/dax/
  validacion_detalle.py  validación de la consulta de listado (antes en src/semantic/detail_list.py)
```

## Decisiones

| Decisión | Por qué |
| --- | --- |
| `runtime_stats` → `src/comun/estadisticas.py` + reexporte | No importa nada del proyecto; lo usan `providers` y `llm`. Los archivos de otros agentes siguen importando la ruta vieja. |
| Una función canónica por **comportamiento**, no por nombre | Las 33 variantes difieren en regex, `%`, `casefold`, NFD/NFKD; agruparlas por lo que hacen y probar cada sustitución con oráculos. |
| Prueba de equivalencia sobre todos los puntos de código relevantes + catálogo real | Las diferencias aparecen en caracteres raros (ß, İ, ligaduras, marcas con `combining` ≠ `Mn`, `0` vs `None`). |
| `indexacion` a `src/catalogo/` **sin reexporte** en `docs_md` | Un reexporte en `docs_md` volvería a crear `docs_md → catalogo → docs_md`. Referencias actualizadas (legado `interfaz.py` incluido, misma cantidad de líneas). |
| `validate_detail_dax` a `src/dax/` | Rompe `dax → semantic`; `detail_list` lo reexporta (dirección `semantic → dax`, permitida). |
| `print` → `logging` solo en constructores de la librería | Los CLIs (`tools/`, bloques `__main__`) llaman a `configurar_registro()` y ven lo mismo por stdout. `diccionario.main` y `powerbi_token.login` escriben para una persona: se quedan (ver tasks). |

## Verificación

- `tests/comun/*` (equivalencias), suites de cada área tocada, `tests.eval.test_eval`.
- Golden master: `tests.resolution.golden.capture --compare <foto del día>`.
- Doctor: `--verificar` y `--actualizar-linea-base` (sin `--forzar`).
