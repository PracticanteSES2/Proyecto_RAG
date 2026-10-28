---
tablero: TABLERO RECEPCION TECNICA
pagina: DETALLE
nombre_funcional: Detalle de solicitudes pendientes por producto
bloque: Día
tablas: [PENDIENTES_RT]
actualizado: 2026-10-28
version: 2
---

# DETALLE

## Propósito
Lista cada solicitud pendiente en Recepción Técnica con su producto, área de servicio, cantidades y horas pendientes, para el seguimiento caso por caso. Se llega desde el botón DETALLE de CANTIDADES y tiene botón INICIO de regreso. Seguimiento de los dos últimos días y hoy (bloque Día). Es una página oculta de Power BI.

## Fuentes de datos
- **PENDIENTES_RT**: Líneas de solicitud de los almacenes 51 y 62 con fecha de documento entre hace dos días y hoy.

## Indicadores
- **Tiempo oportunidad**: Promedio de horas desde el documento de solicitud. AVERAGE(PENDIENTES_RT[TIEMPO_DISPENSACION]), igual que en CANTIDADES.
- **Solicitudes pendientes**: Líneas de solicitud pendientes. DISTINCTCOUNT(PENDIENTES_RT[OID]).

## Visuales
- **Tarjetas de indicadores**: TIEMPO OPORTUNIDAD y SOLICITUDES PENDIENTES.
- **Filtros de la página**: Segmentación de PENDIENTES_RT[CSCFECDOC] (rango de fechas del documento) y de PENDIENTES_RT[GASNOMBRE] (AREA SERVICIO).
- **Tabla de solicitudes**: SOLICITUD, PRODUCTO (descripción corta), AREA SERVICIO, CANTIDAD SOLICITADA, CANTIDAD PENDIENTE y HORAS PENDIENTE (suma de PENDIENTES_RT[TIEMPO_DISPENSACION], en horas), ordenada de más a menos horas.
- **Botón inicio**: Regresa a CANTIDADES.

## Reglas de negocio
- **Cantidades**: CANTIDAD SOLICITADA es la suma de PENDIENTES_RT[CSDCANTID] y CANTIDAD PENDIENTE la de PENDIENTES_RT[CSDCANPEN] de la línea de solicitud.

## Observaciones
- **Área vacía**: En la captura hay solicitudes sin área de servicio.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
