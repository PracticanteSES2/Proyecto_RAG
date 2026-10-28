---
tablero: TABLERO PERFIL DE MORBILIDAD
pagina: PIRAMIDE POBLACIONAL PERIOPERATORIA
nombre_funcional: Pirámide poblacional de los pacientes operados
bloque: Histórico
tablas: []
actualizado: 2026-10-28
version: 1
id_pagina: 5c7b3116b69828e8bef4
---

# PIRAMIDE POBLACIONAL PERIOPERATORIA

## Propósito
Página oculta; por su nombre es la versión perioperatoria de PIRAMIDE POBLACIONAL (edad y sexo de los pacientes operados). Su contenido exacto está por confirmar porque el PBIP no trae sus visuales.

## Fuentes de datos
- **PERIOPERATORIA**: Cirugías con diagnóstico, CMD, GRD, edad a la fecha de cirugía y asegurador. Es la tabla propia de este análisis en el modelo; por confirmar si los visuales de la página la usan.
- **MATRIZ 2024**: El filtro de la página usa esta tabla; por confirmar si los visuales también.

## Visuales
- **Visuales de la página**: Por confirmar. El PBIP no trae su definición.

## Reglas de negocio
- **Filtro de página**: MATRIZ 2024[GRD_R] no está vacío.

## Observaciones
- **Página oculta**: No aparece en la barra de páginas; se llega por botones.
- **Sin documentación del propietario**: Los indicadores y visuales están por confirmar con el dueño del tablero.

## Historial de cambios
- **2026-10-28 · v1**: Borrador a partir del PBIP y del modelo.
