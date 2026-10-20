---
tablero: TABLERO FARMACIA
pagina: SUMINISTROS PENDIENTES
nombre_funcional: Detalle de suministros de medicamentos pendientes
bloque: Día
tablas: [PENDIENTES_FARMACIA, ALMACENES]
actualizado: 2026-10-20
version: 1
---

# SUMINISTROS PENDIENTES

## Propósito
Lista cada orden de medicamento solicitada en los últimos 3 días con su servicio, fechas de solicitud y cierre y tiempo de espera, para detectar demoras y priorizar la dispensación. Seguimiento del día (bloque Día). Se llega desde el botón SUMINISTROS PENDIENTES de INICIO. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **PENDIENTES_FARMACIA**: Órdenes de medicamentos intrahospitalarias de los almacenes 002, 007, 075 y 062, desde hace 3 días hasta hoy.

## Indicadores
- **Oportunidad de dispensación**: Tiempo promedio de dispensación en horas; misma tarjeta de INICIO. Cálculo por confirmar.
- **Suministros pendientes**: Folios con órdenes sin cerrar; probablemente DISTINCTCOUNT(PENDIENTES_FARMACIA[HCNFOLIO]) con FECHA_CIERRE vacía. Por confirmar.
- **Tiempo de solicitud**: Tiempo desde la solicitud hasta el cierre o hasta la actualización. Columna PENDIENTES_FARMACIA[minutos] (en minutos).

## Visuales
- **Tarjetas de indicadores**: OPORTUNIDAD DE DISPENSACIÓN y SUMINISTROS PENDIENTES.
- **Filtros de la página**: ESTADO, ALMACEN y casilla MEDICAMENTO MIPRES.
- **Tabla de suministros**: CONSECUTIVO, MEDICAMENTO, CANTIDAD, SERVICIO, FECHA SOLICITUD, FECHA CIERRE y tiempo de solicitud, ordenada por tiempo de mayor a menor.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Órdenes incluidas**: Órdenes intrahospitalarias (hcsintrah = 1) de tipo 0 (HCPTIPORD = 0).
- **Rango de horas**: 0-6, 6-12, 12-18, 18-24, 24-36 y más de 36 horas, medido hasta el cierre o hasta la actualización.

## Observaciones
- **Campos por confirmar**: La página no está en el PBIP; no se sabe qué columna alimenta el filtro ESTADO ni si CONSECUTIVO es el consecutivo del ingreso (AINCONSEC).
- **Cantidad vacía**: En la captura muchas filas no tienen cantidad.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
