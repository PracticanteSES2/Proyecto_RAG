---
tablero: TABLERO FARMACIA
pagina: SUMINISTROS PENDIENTES
nombre_funcional: Detalle de suministros de medicamentos pendientes
bloque: Día
tablas: [PENDIENTES_FARMACIA, ALMACENES]
actualizado: 2026-10-28
version: 2
---

# SUMINISTROS PENDIENTES

## Propósito
Lista cada orden de medicamento solicitada en los últimos 3 días con su servicio, fechas de solicitud y cierre y tiempo de espera, para detectar demoras y priorizar la dispensación. Seguimiento del día (bloque Día). La página existe oculta en el PBIP, sin visuales; el contenido se describe con la documentación del propietario. El botón SUMINISTROS PENDIENTES de INICIO no está en el PBIP.

## Fuentes de datos
- **PENDIENTES_FARMACIA**: Órdenes de medicamentos intrahospitalarias de los almacenes 002, 007, 075 y 062, desde hace 3 días hasta hoy.

## Indicadores
- **Oportunidad de dispensación**: Tiempo promedio de dispensación en horas, AVERAGE(TIEMPOS_DISPENSACIÓN[OportunidadHor]); misma tarjeta de INICIO, que no está en el PBIP.
- **Suministros pendientes**: Folios con órdenes sin cerrar; DISTINCTCOUNT(PENDIENTES_FARMACIA[HCNFOLIO]) con FECHA_CIERRE vacía, igual que la tarjeta de INICIO.
- **Tiempo de solicitud**: Tiempo en minutos desde la solicitud (FECHA_SOLICITUD) hasta el cierre (FECHA_CIERRE) o hasta la actualización; columna PENDIENTES_FARMACIA[minutos].

## Visuales
- **Tarjetas de indicadores**: OPORTUNIDAD DE DISPENSACIÓN y SUMINISTROS PENDIENTES.
- **Filtros de la página**: ESTADO, ALMACEN y casilla MEDICAMENTO MIPRES.
- **Tabla de suministros**: CONSECUTIVO, MEDICAMENTO, CANTIDAD, SERVICIO, FECHA SOLICITUD, FECHA CIERRE y tiempo de solicitud, ordenada por tiempo de mayor a menor.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Órdenes incluidas**: Órdenes intrahospitalarias (hcsintrah = 1) de tipo 0 (HCPTIPORD = 0) de los almacenes 002, 007, 075 y 062, solicitadas desde hace 3 días hasta hoy.
- **Rango de horas**: 0-6, 6-12, 12-18, 18-24, 24-36 y más de 36 horas, medido hasta el cierre o hasta la actualización.

## Observaciones
- **Campos por confirmar**: La página no tiene visuales en el PBIP. El filtro ESTADO probablemente usa PENDIENTES_FARMACIA[PENDIENTE] (PENDIENTE o DISPENSADO) y MEDICAMENTO MIPRES usa PENDIENTES_FARMACIA[MIPRES]; CONSECUTIVO podría ser AINCONSEC (consecutivo del ingreso). Por confirmar.
- **Cantidad vacía**: En la captura muchas filas no tienen cantidad.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
