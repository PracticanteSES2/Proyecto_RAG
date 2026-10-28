---
tablero: TABLERO RECEPCION TECNICA
pagina: CANTIDADES
nombre_funcional: Solicitudes pendientes de suministro por horas y área de servicio
bloque: Día
tablas: [PENDIENTES_RT]
actualizado: 2026-10-20
version: 1
---

# CANTIDADES

## Propósito
Página de inicio del tablero. Muestra cuántas solicitudes de productos están pendientes en Recepción Técnica, cuántas horas llevan en promedio y cómo se reparten por rango de horas y por área de servicio, para priorizar casos. Seguimiento de los dos últimos días y hoy (bloque Día). Tiene botones a DETALLE y RECEPCIÓN.

## Fuentes de datos
- **PENDIENTES_RT**: Líneas de solicitud de los almacenes 51 y 62 con fecha de documento entre hace dos días y hoy.

## Indicadores
- **Tiempo oportunidad**: Promedio de horas desde el documento de solicitud hasta la actualización. AVERAGE(PENDIENTES_RT[TIEMPO_DISPENSACION]).
- **Solicitudes pendientes**: Líneas de solicitud pendientes. DISTINCTCOUNT(PENDIENTES_RT[OID]).

## Visuales
- **Tarjetas de indicadores**: TIEMPO OPORTUNIDAD (horas) y SOLICITUDES PENDIENTES.
- **Filtro de área servicio**: Lista desplegable de PENDIENTES_RT[GASNOMBRE].
- **Filtro de fechas**: Control deslizante de rango sobre la fecha del documento (CSCFECDOC).
- **Columnas por horas de suministro**: Titulado «PENDIENTES por HORAS SUMINISTRO»; DISTINCTCOUNT de OID por rango de HORAS_SUMINISTRO en orden ascendente.
- **Barras por área servicio**: Titulado «PENDIENTES por AREA SERVICIO»; DISTINCTCOUNT de OID por área, de mayor a menor, sin área vacía.
- **Botones de navegación**: DETALLE abre la página DETALLE; RECEPCIÓN abre la página RECEPCIÓN.

## Reglas de negocio
- **Rangos de horas**: 0-6, 6-12, 12-18 y 18-24 horas sin incluir el límite superior; 24-48 horas incluye 48; más de 48 horas va a «6. 48 o mas horas».

## Observaciones
- **Pendiente sin filtro explícito**: La consulta documentada no filtra cantidad pendiente mayor que cero ni estado de la solicitud; por confirmar cómo se limita a pendientes.
- **Conteo por línea**: SOLICITUDES PENDIENTES cuenta OID de la línea de producto (CPNSOLICID), no el número de solicitud; una solicitud con varios productos cuenta varias veces.
- **Botón RECEPCIÓN**: Aparece en la captura de la documentación pero no en el PBIP disponible.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
