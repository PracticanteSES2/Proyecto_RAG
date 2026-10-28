---
tablero: TABLERO CONTROL FACTURACION
pagina: FACTURADORES
nombre_funcional: Producción de facturación por facturador
bloque: Histórico
tablas: [FACTURADORES, ULT_GESTION, CALENDARIO]
actualizado: 2026-10-28
version: 2
---

# FACTURADORES

## Propósito
Mide la producción de cada facturador: monto total facturado, separado en hospitalario y ambulatorio, ranking por facturador y detalle de facturas. Sirve para evaluar la productividad del equipo de facturación. Análisis histórico por año y mes; se llega desde el botón FACTURADORES de INICIO.

## Fuentes de datos
- **FACTURADORES**: Facturas (SLNFACTUR) no anuladas con fecha de factura desde el 1 de agosto de 2025. Trae ingreso, fechas de ingreso, egreso y factura, tipo de ingreso, entidad, facturador (usuario que generó la factura), rol y estado del facturador, servicio, área de servicio, número de factura, monto (SFATOTFAC) y días del egreso a la factura.

## Indicadores
- **Total facturación**: Suma de FACTURADORES[MONTO_FACTURADO], en pesos.
- **Total facturación hospitalario**: Suma de MONTO_FACTURADO filtrada a una lista fija de 52 facturadores del área hospitalaria en la tarjeta (53 en el gráfico de barras HOSPITALARIO, por lo que ambos pueden diferir), en pesos.
- **Total facturación ambulatorio**: Suma de MONTO_FACTURADO filtrada a una lista fija de 14 facturadores del área ambulatoria.

## Visuales
- **Filtros**: Segmentadores «AREA SERVICIO» (ULT_GESTION[AREA_SERVICIO], sin vacíos), «Date Año» y «Date Mes» (CALENDARIO[Date], que filtra por FACTURADORES[FECHA_FACTURA]); botón de inicio que vuelve a INICIO.
- **Tarjetas**: TOTAL FACTURACION, TOTAL FACTURACION HOSPITALARIO y TOTAL FACTURACION AMBULATORIO.
- **Barras hospitalario**: Gráfico de barras agrupadas «MONTO FACTURADO HOSPITALARIO»: suma de MONTO_FACTURADO por facturador, con la lista hospitalaria de 53 nombres.
- **Barras ambulatorio**: Gráfico de barras agrupadas «MONTO FACTURADO AMBULATORIO»: suma de MONTO_FACTURADO por facturador, con la lista ambulatoria de 14 nombres.
- **Tabla de facturadores**: Tabla sin título con columnas FACTURADOR, SERVICIO, AREA DE SERVICIO (AREA_SERVICIO), FECHA FACTURA y MONTO (suma de MONTO_FACTURADO), con total.

## Reglas de negocio
- **Factura válida**: Solo facturas no anuladas (SFADOCANU vacío o 0).
- **Hospitalario y ambulatorio por lista**: La separación no usa el tipo de ingreso sino listas de nombres de facturadores escritas en los filtros de cada visual. Si entra o sale un facturador hay que actualizar la lista en Power BI.

## Observaciones
- **Totales que no cuadran**: Los facturadores que no están en ninguna lista solo suman en TOTAL FACTURACION; en la captura de la documentación hospitalario más ambulatorio es menor que el total.
- **Columna sin usar**: La consulta trae TIPO_INGRESO y DIAS_EGRESO_A_FACTURA, pero no se usan en los visuales conocidos.
- **Segmentador de área**: El segmentador AREA SERVICIO usa ULT_GESTION[AREA_SERVICIO], y ULT_GESTION no se relaciona con FACTURADORES en el modelo; el segmentador probablemente no filtra las facturas. Debería usar FACTURADORES[AREA_SERVICIO]. Por confirmar.
- **Listas distintas**: Las listas de facturadores hospitalarios difieren entre la tarjeta (52 nombres) y el gráfico de barras (53), y la tabla del PBIP no está filtrada por lista.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
