---
tablero: TABLERO FARMACIA
pagina: STOCK MINIMO
nombre_funcional: Inventario: productos por debajo del stock mínimo
bloque: Día
tablas: [CANTIDAD_MINIMA, ALMACENES]
actualizado: 2026-10-28
version: 2
---

# STOCK MINIMO

## Propósito
Lista los productos de farmacia cuya cantidad disponible en Dinámica está por debajo del stock mínimo, con el faltante y su porcentaje, para priorizar la reposición y prevenir desabastecimientos. Muestra el estado actual del inventario (bloque Día). La documentación la llama «Inventario - Stock mínimo»; corresponde al botón INVENTARIO de INICIO.

## Fuentes de datos
- **CANTIDAD_MINIMA**: Productos por almacén con código (CODIGO), nombre (DESCRIPCION), stock mínimo (STOCKCANTI), existencia en Dinámica (CANDINAMICA) y faltante (FALTANTE, CANFALTANTE).
- **ALMACENES**: Lista de almacenes para el filtro.

## Indicadores
- **Faltante real**: Unidades que faltan para llegar al stock mínimo: [FALTANTE_REAL] = AVERAGE(CANTIDAD_MINIMA[STOCKCANTI]) menos [TOTAL_DINAMICA]. Positivo es faltante; negativo, excedente.
- **Porcentaje de faltante**: Faltante sobre el stock mínimo: [%FALTANTE_REAL] = [FALTANTE_REAL] / AVERAGE(STOCKCANTI); por ejemplo 15 de 20 es 75 %. Existe también la columna CANTIDAD_MINIMA[%FALTANTE].

## Visuales
- **Filtros de la página**: En el PBIP solo existe la lista desplegable ALMACEN (ALMACENES[IALNOMBRE]); la lista MEDICAMENTO de la documentación no está en el PBIP.
- **Tabla de stock mínimo**: CODIGO, PRODUCTO, STOCK MINIMO, CANTIDAD DINAMICA, FALTANTE_REAL y %FALTANTE, ordenada por %FALTANTE de mayor a menor.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Almacenes excluidos**: Filtro de página que excluye el almacén «STOCK URGENCIAS» y los valores vacíos de ALMACENES[IALNOMBRE].

## Observaciones
- **Navegación por confirmar**: El botón INVENTARIO de INICIO lleva a «Duplicado de STOCK MINIMO», no a esta página; ambas están ocultas en modo vista y tienen el mismo filtro de página.
- **Columnas por confirmar**: El PBIP solo trae el filtro de almacén y el botón de regreso a INICIO; la tabla de stock mínimo se describe con la captura de la documentación y no está en el PBIP.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
