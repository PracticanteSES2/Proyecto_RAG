---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: INTERCONSULTAS DIA
nombre_funcional: Interconsultas del día
bloque: Día
tablas: [INTERCONSULTA_DIA]
actualizado: 2026-10-20
version: 1
---

# INTERCONSULTAS DIA

## Propósito
En Power BI esta página se llama INTERCONSULTAS, igual que la página histórica; aquí se documenta como INTERCONSULTAS DIA para distinguirlas. Muestra las interconsultas solicitadas desde urgencias que esperan respuesta de otra especialidad y las ya respondidas, con semáforo. Todos los tiempos están en horas. Se llega desde el botón de interconsultas de RESUMEN_D y el botón superior izquierdo regresa a RESUMEN_D.

## Fuentes de datos
- **INTERCONSULTA_DIA**: Interconsultas solicitadas desde urgencias en los últimos 3 días; tabla en DirectQuery.

## Indicadores
- **Tiempo de respuesta de interconsulta**: Horas entre el folio de solicitud y el folio de respuesta; sin respuesta, hasta la hora actual. Columna INTERCONSULTA_DIA[TIEMPO_RESPUESTA_INTERCONSULTA].

## Visuales
- **Tabla en espera interconsulta**: Interconsultas sin respuesta con hasta 48 horas de espera. Columnas DOCUMENTO, NOMBRE_PACIENTE, ESPECIALIDAD y TIEMPO ESPERA.
- **Tabla respuestas a interconsulta**: Titulada «RESPUESTAS A INTERCONSULTA ÚLTIMAS 24 HORAS»; interconsultas respondidas en 24 horas o menos. Columnas DOCUMENTO, NOMBRE_PACIENTE, ESPECIALIDAD, FECHA SOLICITUD, FECHA RESPUESTA y TIEMPO ESPERA.

## Reglas de negocio
- **Semáforo de interconsultas**: En ambas tablas, verde de 0 a 12 horas, amarillo de más de 12 hasta 24 y rojo de más de 24.
- **Interconsultas consideradas**: Solicitadas desde el área de urgencias (área 2) con folio de solicitud de hoy o de los 3 días anteriores.
- **Interconsulta en espera**: No tiene respuesta asociada (OID_RESPUESTA vacío).
- **Especialidad mostrada**: Es la especialidad solicitada (GENESPECI.GEEDESCRI).

## Observaciones
- **Título de la tabla de respuestas**: El filtro no limita a las respuestas de las últimas 24 horas sino a las respondidas en 24 horas o menos, solicitadas en los últimos 3 días.
- **Esperas de más de 48 horas ocultas**: Las interconsultas sin respuesta con más de 48 horas no aparecen en la tabla de espera. Por confirmar si es intencional.
- **Nombre repetido**: Se recomienda renombrar la página en Power BI (por ejemplo INTERCONSULTAS DIA) para no confundirla con la histórica.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
