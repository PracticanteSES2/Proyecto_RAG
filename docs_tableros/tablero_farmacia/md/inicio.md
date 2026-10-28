---
tablero: TABLERO FARMACIA
pagina: INICIO
nombre_funcional: Resumen de farmacia: oportunidad, pendientes, inventario mínimo y vencimientos
bloque: Día
tablas: [PENDIENTES_FARMACIA, TIEMPOS_DISPENSACIÓN, CANTIDAD_MINIMA, PRODUCTOS_VENCIDOS, VENCIMIENTO_PRODUCTOS, ALMACENES]
actualizado: 2026-10-28
version: 2
---

# INICIO

## Propósito
Página principal del tablero de farmacia. Resume con tarjetas la oportunidad de dispensación, los suministros pendientes, los productos bajo inventario mínimo y los medicamentos vencidos, y muestra los pendientes por horas de espera y los productos por meses para vencer. Seguimiento del estado actual (bloque Día). Tiene los botones hacia las demás páginas.

## Fuentes de datos
- **PENDIENTES_FARMACIA**: Órdenes de medicamentos de los últimos 3 días y hoy.
- **CANTIDAD_MINIMA**: Productos con marca de falta frente al stock mínimo.
- **PRODUCTOS_VENCIDOS**: Ajustes por medicamentos vencidos de los últimos 3 meses.
- **VENCIMIENTO_PRODUCTOS**: Lotes con meses para vencer.

## Indicadores
- **Oportunidad de dispensación**: Tiempo promedio de dispensación en horas, AVERAGE(TIEMPOS_DISPENSACIÓN[OportunidadHor]), entre el folio y el documento de suministro. La tarjeta no está en el PBIP; el cálculo viene de la página OPORTUNIDAD DISPENSACIÓN.
- **Número de suministros pendientes**: Folios con órdenes sin cerrar. DISTINCTCOUNT(PENDIENTES_FARMACIA[HCNFOLIO]) con FECHA_CIERRE vacía.
- **Productos por debajo de inventario mínimo**: Productos con existencia en Dinámica menor que el stock mínimo. DISTINCTCOUNT(CANTIDAD_MINIMA[CODIGO]) con CANTIDAD_MINIMA[falta] = 1, sin el almacén STOCK URGENCIAS.
- **Medicamentos vencidos**: Unidades dadas de baja por vencimiento. SUM(PRODUCTOS_VENCIDOS[iddcantid]).

## Visuales
- **Tarjetas de indicadores**: OPORTUNIDAD DE DISPENSACIÓN, NÚMERO DE SUMINISTROS PENDIENTES, PRODUCTOS POR DEBAJO DE INVENTARIO MINIMO y MEDICAMENTOS VENCIDOS.
- **Filtro de almacén**: Lista desplegable ALMACEN (ALMACENES[IALNOMBRE]).
- **Columnas de pendientes por horas**: Gráfico de columnas agrupadas; eje HORAS_SUMINISTRO (rótulo TIEMPO (HORAS)), valor DISTINCTCOUNT de HCNFOLIO (PENDIENTES), solo pendientes (FECHA_CIERRE vacía).
- **Columnas por vencimiento en meses**: Gráfico de columnas agrupadas; eje VENCIMIENTO_PRODUCTOS[mes] (VENCIMIENTO EN MESES), valor COUNT(IFICANTID) (CANTIDAD); cuenta lotes, no unidades.
- **Botones de navegación**: MEDICAMENTOS VENCIDOS (a la página del mismo nombre), TIEMPO DE DISPENSACIÓN (a OPORTUNIDAD DISPENSACIÓN) e INVENTARIO (a «Duplicado de STOCK MINIMO»); SUMINISTROS PENDIENTES está en la documentación pero no en el PBIP.

## Reglas de negocio
- **Pendiente**: Orden sin fecha de cierre.
- **Exclusión de stock urgencias**: La tarjeta de inventario mínimo excluye el almacén «STOCK URGENCIAS».

## Observaciones
- **Hueco en 36 horas**: El rango 5 llega hasta menos de 36 horas y el 6 empieza en más de 36, así que una espera de exactamente 36 horas queda sin rango; en la captura aparece una columna «(En blanco)».
- **Vencimiento cuenta filas**: CANTIDAD por VENCIMIENTO EN MESES cuenta registros (COUNT de IFICANTID), no suma unidades.
- **Vencidos en blanco**: En la captura la tarjeta MEDICAMENTOS VENCIDOS de INICIO sale «(En blanco)» mientras la página MEDICAMENTOS VENCIDOS muestra 88. Por confirmar.
- **Visuales fuera del PBIP**: La tarjeta OPORTUNIDAD DE DISPENSACIÓN y el botón SUMINISTROS PENDIENTES están en la captura de la documentación pero no en el PBIP actual.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
