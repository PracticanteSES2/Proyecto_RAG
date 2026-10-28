---
tablero: TABLERO FARMACIA
pagina: Duplicado de STOCK MINIMO
nombre_funcional: Copia oculta de la página de inventario por debajo del stock mínimo
bloque: Día
tablas: [ALMACENES]
actualizado: 2026-10-28
version: 1
---

# Duplicado de STOCK MINIMO

## Propósito
Copia de la página STOCK MINIMO, oculta en modo vista y sin visuales en el PBIP. Es el destino del botón INVENTARIO de INICIO. Se conserva con el mismo filtro de página que STOCK MINIMO.

## Fuentes de datos
- **ALMACENES**: Lista de almacenes sobre la que actúa el filtro de página.

## Reglas de negocio
- **Almacenes excluidos**: Filtro de página que excluye el almacén «STOCK URGENCIAS» y los valores vacíos de ALMACENES[IALNOMBRE].

## Observaciones
- **Página sin visuales**: En el PBIP la página no tiene visuales; el contenido de inventario mínimo se describe en STOCK MINIMO. Por confirmar si es la página vigente del botón INVENTARIO.

## Historial de cambios
- **2026-10-28 · v1**: Documentación inicial a partir del PBIP.
