---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: INTERCONSULTAS HISTORICO
nombre_funcional: Interconsultas, histórico
bloque: Histórico
tablas: [INTERCONSULTA]
actualizado: 2026-10-20
version: 1
---

# INTERCONSULTAS HISTORICO

## Propósito
En Power BI esta página se llama INTERCONSULTAS, igual que la página del día; aquí se documenta como INTERCONSULTAS HISTORICO para distinguirlas. Muestra el total de interconsultas solicitadas desde urgencias, las respondidas, el porcentaje de atención y, por año y mes, la cantidad y el tiempo promedio de respuesta en minutos. Se llega desde RESUMEN.

## Fuentes de datos
- **INTERCONSULTA**: Interconsultas solicitadas desde el área de urgencias (área 2) desde el 01/01/2023; FECHA es la fecha del folio de solicitud; tabla en Import.

## Indicadores
- **Interconsultas solicitadas**: Número de interconsultas solicitadas. SUM(INTERCONSULTA[SOLICITUDES]).
- **Interconsultas respondidas**: Número de interconsultas con respuesta. SUM(INTERCONSULTA[RESPUESTAS]).
- **Porcentaje de atención**: Respondidas sobre solicitadas. Medida %ATENDIDO = SUM(INTERCONSULTA[RESPUESTAS]) / SUM(INTERCONSULTA[SOLICITUDES]).
- **Tiempo promedio de respuesta a interconsulta**: Minutos entre el folio de solicitud y el folio de respuesta, solo respondidas. AVERAGE(INTERCONSULTA[TIEMPO_RESPUESTA_INTERCONSULTA]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de solicitud.
- **Segmentador de especialidad**: Filtra por la especialidad solicitada, INTERCONSULTA[GEEDESCRI].
- **Tarjetas de solicitadas, respondidas y porcentaje**: Muestran los tres primeros indicadores.
- **Gráfico de interconsultas y tiempo por mes**: Columnas con el conteo distinto de OID_SOLICITUD y línea con el tiempo promedio de respuesta en minutos, por año y mes. Su filtro sobre CONSULTA_URGENCIAS[TIPO_TRIAGE] no tiene efecto.
- **Botón de regreso**: Lleva a RESUMEN.

## Reglas de negocio
- **Tiempo solo de respondidas**: El tiempo de respuesta histórico se mide en minutos y solo existe para interconsultas respondidas; en INTERCONSULTAS DIA se mide en horas.

## Observaciones
- **Interconsultas de hoy excluidas**: La sentencia compara la fecha y hora del folio con la fecha de hoy sin hora, por lo que excluye las solicitadas hoy después de la medianoche. Efecto menor.
- **Nombre repetido**: Se recomienda renombrar la página en Power BI para no confundirla con la del día.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
