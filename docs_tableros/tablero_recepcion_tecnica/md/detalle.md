---
tablero: TABLERO RECEPCION TECNICA
pagina: DETALLE
nombre_funcional: Detalle de solicitudes pendientes por producto
bloque: Día
tablas: [PENDIENTES_RT]
actualizado: 2026-10-20
version: 1
---

# DETALLE

## Propósito
Lista cada solicitud pendiente en Recepción Técnica con su producto, área de servicio, cantidades y horas pendientes, para el seguimiento caso por caso. Se llega desde el botón DETALLE de CANTIDADES y tiene botón INICIO de regreso. Seguimiento de los dos últimos días y hoy (bloque Día). Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **PENDIENTES_RT**: Líneas de solicitud de los almacenes 51 y 62 con fecha de documento entre hace dos días y hoy.

## Indicadores
- **Tiempo oportunidad**: Promedio de horas desde el documento de solicitud. AVERAGE(PENDIENTES_RT[TIEMPO_DISPENSACION]); por confirmar que sea el mismo campo de CANTIDADES.
- **Solicitudes pendientes**: Conteo de líneas de solicitud pendientes; por confirmar que sea DISTINCTCOUNT(PENDIENTES_RT[OID]).

## Visuales
- **Tarjetas de indicadores**: TIEMPO OPORTUNIDAD y SOLICITUDES PENDIENTES.
- **Filtros de la página**: Rango de fechas del documento y AREA SERVICIO.
- **Tabla de solicitudes**: SOLICITUD, PRODUCTO (descripción corta), AREA SERVICIO, CANTIDAD SOLICITADA, CANTIDAD PENDIENTE y HORAS PENDIENTE, ordenada de más a menos horas.
- **Botón inicio**: Regresa a CANTIDADES.

## Reglas de negocio
- **Cantidades**: CANTIDAD SOLICITADA corresponde a CSDCANTID y CANTIDAD PENDIENTE a CSDCANPEN de la línea de solicitud (por confirmar en el PBIP).

## Observaciones
- **Sin PBIP de la página**: El PBIP disponible no trae los visuales de esta página; la descripción sale de la documentación y su captura.
- **Área vacía**: En la captura hay solicitudes sin área de servicio.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
