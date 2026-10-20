---
tablero: TABLERO FARMACIA
pagina: STOCK MINIMO
nombre_funcional: Inventario: productos por debajo del stock mínimo
bloque: Día
tablas: [CANTIDAD_MINIMA, ALMACENES]
actualizado: 2026-10-20
version: 1
---

# STOCK MINIMO

## Propósito
Lista los productos de farmacia cuya cantidad disponible en Dinámica está por debajo del stock mínimo, con el faltante y su porcentaje, para priorizar la reposición y prevenir desabastecimientos. Muestra el estado actual del inventario (bloque Día). La documentación la llama «Inventario - Stock mínimo»; corresponde al botón INVENTARIO de INICIO.

## Fuentes de datos
- **CANTIDAD_MINIMA**: Productos con código, nombre, stock mínimo, cantidad en Dinámica y faltante. Consulta no documentada.
- **ALMACENES**: Lista de almacenes para el filtro.

## Indicadores
- **Faltante real**: Unidades que faltan para llegar al stock mínimo; según la captura, STOCK MINIMO menos CANTIDAD DINAMICA.
- **Porcentaje de faltante**: Faltante sobre el stock mínimo; según la captura, FALTANTE_REAL dividido por STOCK MINIMO (por ejemplo 15 de 20 = 75 %).

## Visuales
- **Filtros de la página**: Listas desplegables ALMACEN y MEDICAMENTO.
- **Tabla de stock mínimo**: CODIGO, PRODUCTO, STOCK MINIMO, CANTIDAD DINAMICA, FALTANTE_REAL y %FALTANTE, ordenada por %FALTANTE de mayor a menor.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Almacenes excluidos**: Filtro de página que quita el almacén «STOCK URGENCIAS» y los almacenes vacíos.

## Observaciones
- **Navegación por confirmar**: En el PBIP el botón INVENTARIO de INICIO apunta a una página que no está en el PBIP; esta página STOCK MINIMO existe oculta y podría ser una versión distinta.
- **Columnas por confirmar**: El PBIP solo trae el filtro de almacén y el botón de esta página; la tabla y sus cálculos se describen con la captura de la documentación.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
