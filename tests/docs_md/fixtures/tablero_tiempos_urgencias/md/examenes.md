---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: EXAMENES
nombre_funcional: Exámenes de laboratorio, histórico
bloque: Histórico
tablas: [EXAMENES]
actualizado: 2026-10-20
version: 1
---

# EXAMENES

## Propósito
Muestra por año y mes la cantidad de solicitudes de exámenes con respuesta y el tiempo promedio de respuesta en minutos. Se llega desde RESUMEN.

## Fuentes de datos
- **EXAMENES**: Un examen con respuesta por ingreso, desde el 01/01/2023, de folios de las áreas 2 (urgencias) y 42; FECHA es la fecha de la solicitud; tabla en Import.

## Indicadores
- **Tiempo promedio de respuesta a exámenes**: Minutos entre la solicitud del examen y la respuesta. AVERAGE(EXAMENES[TIEMPO_RESPUESTA]).
- **Cantidad de solicitudes**: Número de filas, una por ingreso con examen respondido. SUM(EXAMENES[CANT_EXAMENES]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de la solicitud.
- **Tarjeta tiempo de respuesta**: Tiempo promedio de respuesta a exámenes en minutos.
- **Gráfico de solicitudes y tiempo por mes**: Columnas CANTIDAD SOLICITUDES y línea TIEMPO DE RESPUESTA PROMEDIO en minutos, por año y mes.
- **Botón de regreso**: Lleva a RESUMEN.

## Reglas de negocio
- **Solo exámenes respondidos**: EXAMENES solo carga solicitudes con respuesta (unión interna con DIM_RESPUESTA_EXAMENES).
- **Una fila por ingreso**: Se conserva solo la primera respuesta de cada ingreso; la cantidad de solicitudes es en realidad la cantidad de ingresos con al menos un examen respondido.

## Observaciones
- **Sin filtro de laboratorio**: A diferencia de LABORATORIOS_DIA (área 15), la sentencia no filtra el área de laboratorio y podría incluir otros tipos de examen. Por confirmar.
- **Área 42**: El área de servicio 42 no está identificada. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
