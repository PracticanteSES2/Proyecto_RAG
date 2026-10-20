---
tablero: TABLERO CONTROL FACTURACION
pagina: FACTURADORES
nombre_funcional: Producción de facturación por facturador
bloque: Histórico
tablas: [FACTURADORES, ULT_GESTION, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# FACTURADORES

## Propósito
Mide la producción de cada facturador: monto total facturado, separado en hospitalario y ambulatorio, ranking por facturador y detalle de facturas. Sirve para evaluar la productividad del equipo de facturación. Análisis histórico por año y mes; se llega desde el botón FACTURADORES de INICIO.

## Fuentes de datos
- **FACTURADORES**: Facturas (SLNFACTUR) no anuladas con fecha de factura desde el 1 de agosto de 2025. Trae ingreso, fechas de ingreso, egreso y factura, tipo de ingreso, entidad, facturador (usuario que generó la factura), rol y estado del facturador, servicio, área de servicio, número de factura, monto (SFATOTFAC) y días del egreso a la factura.

## Indicadores
- **Total facturación**: Suma de FACTURADORES[MONTO_FACTURADO], en pesos.
- **Total facturación hospitalario**: Suma de MONTO_FACTURADO filtrada a una lista fija de 52 facturadores del área hospitalaria.
- **Total facturación ambulatorio**: Suma de MONTO_FACTURADO filtrada a una lista fija de 14 facturadores del área ambulatoria.

## Visuales
- **Filtros**: Segmentadores AREA SERVICIO (ULT_GESTION[AREA_SERVICIO], sin vacíos), Año y Mes; botón de inicio.
- **Tarjetas**: TOTAL FACTURACION, TOTAL FACTURACION HOSPITALARIO y TOTAL FACTURACION AMBULATORIO.
- **Barras hospitalario**: Titulado «MONTO FACTURADO HOSPITALARIO»; suma de monto por facturador, de mayor a menor. No está en el PBIP local; por confirmar que use la lista hospitalaria.
- **Barras ambulatorio**: Titulado «MONTO FACTURADO AMBULATORIO»; suma de monto por facturador de la lista ambulatoria.
- **Tabla de facturadores**: Columnas FACTURADOR, SERVICIO, AREA DE SERVICIO, FECHA FACTURA y MONTO, con total.

## Reglas de negocio
- **Factura válida**: Solo facturas no anuladas (SFADOCANU vacío o 0).
- **Hospitalario y ambulatorio por lista**: La separación no usa el tipo de ingreso sino listas de nombres de facturadores escritas en los filtros de cada visual. Si entra o sale un facturador hay que actualizar la lista en Power BI.

## Observaciones
- **Totales que no cuadran**: Los facturadores que no están en ninguna lista solo suman en TOTAL FACTURACION; en la captura de la documentación hospitalario más ambulatorio es menor que el total.
- **Columna sin usar**: La consulta trae TIPO_INGRESO y DIAS_EGRESO_A_FACTURA, pero no se usan en los visuales conocidos.
- **Filtro de área**: El segmentador de área usa ULT_GESTION en lugar de FACTURADORES[AREA_SERVICIO]; por confirmar la relación entre ambas tablas.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
