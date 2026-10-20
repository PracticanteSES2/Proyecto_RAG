---
tablero: BRIEFING HOSPITALARIO
pagina: ATENCIONES POR ASEGURADOR
nombre_funcional: Atenciones institucionales por mes, servicio y asegurador desde 2025
bloque: Histórico
tablas: [ATENCIONES_SERVICIO]
actualizado: 2026-10-20
version: 1
---

# ATENCIONES POR ASEGURADOR

## Propósito
Analiza el volumen de atenciones de la institución desde enero de 2025: total, evolución mensual comparando años y distribución por servicio y por asegurador. Sirve para ver tendencias de demanda y la concentración por entidad. Se llega desde el botón ATENCIONES POR SERVICIO de la página INGRESOS Y EGRESOS.

## Fuentes de datos
- **ATENCIONES_SERVICIO**: Servicios prestados (slnserpro) agrupados por fecha, área de servicio (GASNOMBRE) y asegurador (TERNOMCOM), con el número de ingresos distintos atendidos. Desde el 1 de enero de 2025.

## Indicadores
- **Total de atenciones**: Suma de atenciones del periodo filtrado. SUM(ATENCIONES_SERVICIO[TOTAL_ATENCIONES]).
- **Atención**: Cada ingreso distinto atendido en un día, en un área de servicio y para un asegurador (COUNT DISTINCT AINCONSEC por fecha, servicio y asegurador).

## Visuales
- **Tarjeta TOTAL DE ATENCIONES**: Total según los filtros aplicados.
- **Segmentadores**: ASEGURADOR, SERVICIO, Año y Mes.
- **TOTAL DE ATENCIONES**: Gráfico de líneas por mes con una línea por año.
- **Atenciones por servicio**: Barras con las atenciones por servicio, de mayor a menor.
- **Atenciones por asegurador**: Barras con las atenciones por asegurador, de mayor a menor.

## Reglas de negocio
- **Periodo**: Servicios con fecha (SERFECSER) desde el 2025-01-01.
- **Servicio bloqueado**: Filtro de página que excluye el servicio BLOQUEADO.

## Observaciones
- **Suma de atenciones**: Al sumar días, servicios o aseguradores, un mismo ingreso atendido varios días o en varias áreas se cuenta varias veces; el total es de atenciones, no de pacientes.
- **Nombre de la página**: La documentación la llama ATENCIONES POR ASEGURADORA y el botón dice ATENCIONES POR SERVICIO; en el PBIP la página es ATENCIONES POR ASEGURADOR.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
