---
tablero: TABLERO PERFIL DE MORBILIDAD
pagina: ATENCIONES AMBULATORIAS
nombre_funcional: Inicio del análisis de atenciones ambulatorias
bloque: Histórico
tablas: []
actualizado: 2026-10-28
version: 1
id_pagina: 2deb1b17535a67916ca0
---

# ATENCIONES AMBULATORIAS

## Propósito
Página oculta del análisis de consultas ambulatorias; se llega desde el botón ATENCIONES AMBULATORIAS de INICIO. Su contenido exacto está por confirmar porque el PBIP no trae sus visuales y la documentación del propietario no la describe.

## Fuentes de datos
- **AMBULATORIO**: Consultas ambulatorias cumplidas con diagnóstico principal. Es la tabla propia de este análisis en el modelo; por confirmar si los visuales de la página la usan.
- **MATRIZ 2024**: El filtro de la página usa esta tabla; por confirmar si los visuales también.

## Visuales
- **Visuales de la página**: Por confirmar. El PBIP no trae su definición.

## Reglas de negocio
- **Filtro de página**: MATRIZ 2024[GRD_OK] no está vacío.

## Observaciones
- **Página oculta**: No aparece en la barra de páginas; se llega por botones.
- **Sin documentación del propietario**: Los indicadores y visuales están por confirmar con el dueño del tablero.

## Historial de cambios
- **2026-10-28 · v1**: Borrador a partir del PBIP y del modelo.
