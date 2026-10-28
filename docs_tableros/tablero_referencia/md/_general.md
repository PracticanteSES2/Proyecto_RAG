---
tablero: TABLERO REFERENCIA
pagina: GENERAL
nombre_funcional: Seguimiento del proceso de referencia (recepción y remisión de pacientes)
bloque: General
tablas: [REFERENCIA, DETALLE_REMISIONES, DETALLE_RECEPCIONES, CONTRARREFERENCIA]
actualizado: 2026-10-28
version: 2
---

# GENERAL

## Propósito
Hace seguimiento al proceso de referencia de pacientes. La parte de recepción muestra las solicitudes de otras instituciones para enviar pacientes al hospital: volumen, tiempo de respuesta, aceptación y causas de no aceptación. La parte de remisión muestra los pacientes del hospital que se remiten a otras instituciones. INICIO es la página principal y lleva a los detalles de no aceptados, aceptados, seguimiento de recepción y remisión.

## Fuentes de datos
- **REFERENCIA**: Solicitudes de recepción (RECEPCIONES_DW) con llamada en los últimos 30 días, con su causa de no aceptación (SEG_RECEPCIONES) y la fecha de no aceptación (HISTORICO_RECEPCIONES_DW). Alimenta INICIO, DETALLE NO ACEPTADOS RECEPCION, DETALLE ACEPTADOS RECEPCION y SEGUIMIENTO DE RECEPCION.
- **DETALLE_REMISIONES**: Anotaciones de seguimiento de remisiones (HISTORICO_REMISIONES_DW) registradas desde el 1 de enero de 2023. Alimenta DETALLE REMISION y SEGUIMIENTOS REMISION.
- **CONTRARREFERENCIA**: Remisiones del hospital a otras instituciones (SEGUIMIENTO_REMISIONES_DW) con ingreso en los últimos 90 días, con TIEMPO_RESPUESTA y RANGO_TIEMPO. Alimenta DETALLE REMISION y SEGUIMIENTOS REMISION.
- **DETALLE_RECEPCIONES**: Anotaciones de seguimiento de las solicitudes de recepción (OBSERVACIONES_RECEPCION_DW) desde el 1 de enero de 2023. Alimenta DETALLE_RECEPCIONES.

## Definiciones
- **Recepción**: Solicitud que hace otra institución (prestador) para remitir un paciente al hospital; se registra con la fecha y hora de la llamada (FECHALLAMADA).
- **No aceptado**: Solicitud de recepción que el hospital rechaza; queda en estado 3 y con una causa de no aceptación (por ejemplo supera la capacidad instalada, no disponibilidad de cama, aceptado por otra institución).
- **Aceptado**: Solicitud de recepción con fecha de aceptación (FechaAceptado).
- **Tiempo de respuesta**: Horas entre la llamada y la fecha de no aceptación; si no la hay, la de aceptación; si no hay ninguna, hasta hoy. Columna REFERENCIA[TIEMPO_REMISION].
- **Rango de remisión**: Agrupación del tiempo de respuesta: 0-24 HORAS, 24-72 HORAS, 72-120 HORAS y MAYOR A 120 HORAS. Columna REFERENCIA[RANGO_REMISION].
- **Rango de edad**: 0-17 AÑOS, 18 A 65 AÑOS y MAYORES DE 65 AÑOS según la edad en años (ANOS). Columna REFERENCIA[RANGO_EDAD].
- **Remisión**: Solicitud del hospital para trasladar a uno de sus pacientes a otra institución; tiene estado (por ejemplo Registrado, Aceptado Remision, Cancelado), servicio de origen, EPS y fechas de remisión y aceptación.

## Reglas de negocio
- **Ventana de 30 días**: Las páginas de recepción solo contienen solicitudes con llamada posterior a la fecha actual menos 30 días; además tienen un filtro de rango de fechas.
- **Causa en mayúsculas**: La causa de no aceptación se muestra en mayúsculas mediante la columna CAUSA_MAYUSC = UPPER(REFERENCIA[CAUSA]).

## Observaciones
- **Nombres de página**: Las páginas del informe son INICIO, DETALLE NO ACEPTADOS RECEPCION, DETALLE ACEPTADOS RECEPCION, DETALLE_RECEPCIONES (SEGUIMIENTO DE RECEPCION en la documentación del propietario), DETALLE REMISION (SEGUIMIENTO DE REMISION en la documentación) y SEGUIMIENTOS REMISION. El PBIP local no incluye los visuales.
- **Solicitudes sin respuesta**: Para solicitudes sin aceptación ni rechazo el tiempo de respuesta crece hasta hoy, lo que eleva el tiempo promedio de respuesta. Por confirmar si deben excluirse.
- **Llamadas de hoy**: TODAY() corresponde a la medianoche; una solicitud sin respuesta llamada hoy da horas negativas y queda sin rango de remisión.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
