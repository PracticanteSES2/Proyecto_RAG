# Documentación viva de tableros (`src/docs_md`)

Objetivo: que la documentación de cada tablero sea corta, estándar y se mantenga al día sin esfuerzo.
Quien cambia un tablero escribe una nota informal ("le subí el semáforo de egresos a 45 min");
MedGemma propone el cambio sobre la sección exacta del .md; una persona lo aprueba; el RAG se reindexa.

## Formato (un .md por página del tablero)

Ubicación: `data/raw/<source_group>/md/` (el mismo `source_group` del `manifest.json`).
`_general.md` describe el tablero completo (bloque `General`); cada página de Power BI tiene su archivo.
La implementación de referencia es `formato.py` (`parsear`, `serializar`, `validar`, `aplicar_operaciones`).
Ejemplo completo: `tests/docs_md/fixtures/tablero_tiempos_urgencias/md/consultas_dia.md`.

Secciones y orden (las vacías se omiten, salvo Propósito e Historial):

| Página | General | Contenido |
|---|---|---|
| Propósito | Propósito | 2 a 4 líneas: qué muestra, para qué sirve, desde dónde se llega |
| Fuentes de datos | Fuentes de datos | una entrada por tabla u origen |
| Indicadores | — | una entrada por indicador: qué mide, unidad, cálculo (columna o DAX) |
| Visuales | — | una entrada por visual o grupo de visuales |
| — | Definiciones | términos y definiciones de tiempos compartidas por todo el tablero |
| Reglas de negocio | Reglas de negocio | filtros, exclusiones, semáforos, criterios |
| Observaciones | Observaciones | inconsistencias y puntos «Por confirmar» |
| Historial de cambios | Historial de cambios | lo escribe el sistema, nunca el modelo |

## Lineamientos de redacción (los sigue también MedGemma)

1. Cada entrada es `- **Nombre corto**: texto.` en una sola línea. El nombre identifica la entrada; no se repite en su sección.
2. Frases cortas, en español, en presente, terminadas en punto. Nada de adornos ("permite analizar el comportamiento…").
3. Todo tiempo dice su unidad (minutos u horas) y entre qué eventos se mide.
4. Los nombres técnicos van tal cual: páginas en MAYÚSCULAS como en Power BI, columnas como `TABLA[COLUMNA]`.
5. Una entrada por hecho. Si algo cambia, se modifica la entrada existente; no se agregan duplicados.
6. Lo que no se sabe se marca «Por confirmar»; no se inventa.
7. Sin datos de pacientes (nombres, documentos).

## Contratos entre módulos

| Módulo | Función | Responsable |
|---|---|---|
| `formato.py` | parsear / serializar / validar / aplicar_operaciones / diferencias | base (hecho) |
| `repositorio.py` | listar_tableros / listar_paginas / leer_pagina / guardar_pagina | base (hecho) |
| `actualizador.py` | proponer_cambio(nota, source_group, pagina=None, llm=None, cambios_pbip=None) -> Propuesta; aplicar_propuesta(propuesta, autor) | agente actualizador |
| `indexacion.py` | reindexar_grupo(source_group, qdrant_client=None) -> dict | agente ingesta |
| `pbip.py` | extraer_hechos / comparar / esqueleto (+ guardar_instantanea / cambios_desde_instantanea; acepta PBIP o .pbix PBIR) | agente pbip |
| `src/ingestion` | leer `md/` y producir el JSON normalizado del RAG | agente ingesta |
| `pages/` (Streamlit) | ver documentación, proponer cambio, aprobar, reindexar | agente interfaz |

Operaciones que devuelve MedGemma (JSON):

```json
{"pagina": "EGRESOS DIA",
 "operaciones": [{"accion": "modificar", "seccion": "Reglas de negocio",
                  "entrada": "Semáforo de egresos", "texto": "Verde de 0 a 45 minutos, ..."}],
 "resumen": "Se cambió el umbral verde del semáforo de egresos a 45 minutos.",
 "dudas": []}
```

`accion`: agregar | modificar | eliminar. `Propósito` solo admite `modificar` con el texto completo.
El historial y la versión los actualiza `aplicar_operaciones`.
