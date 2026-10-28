---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: TIEMPO HOSPI
nombre_funcional: Tiempo para hospitalización, histórico
bloque: Histórico
tablas: [HISTORICO_HOSP]
actualizado: 2026-10-20
version: 1
---

# TIEMPO HOSPI

## Propósito
Muestra el tiempo promedio, en horas, entre la admisión del paciente en urgencias y la asignación de cama de hospitalización, y su evolución por año y mes desde 2024. Se llega desde RESUMEN.

## Fuentes de datos
- **HISTORICO_HOSP**: Solicitudes de hospitalización (categoría 188, servicio 1) del área de urgencias con cama asignada desde el 01/01/2024; FECHA es la fecha de asignación de cama; tabla en Import.

## Indicadores
- **Tiempo promedio para hospitalización**: Horas entre la admisión (AINFECING) y la asignación de cama (FecAsigCama). AVERAGE(HISTORICO_HOSP[TIEMPO_HOSPI]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de asignación de cama.
- **Tarjeta tiempo para hospitalización**: Tiempo promedio para hospitalización en horas.
- **Gráfico de líneas por mes**: Promedio de HISTORICO_HOSP[TIEMPO_HOSPI] en horas por año y mes.
- **Botón de regreso**: Lleva a RESUMEN.

## Reglas de negocio
- **Intervalo distinto al del día**: Este indicador mide desde la admisión, mientras que HOSPITALIZACION DIA mide desde la solicitud de hospitalización; no son comparables directamente.

## Observaciones
- **Columna en minutos sin uso**: HISTORICO_HOSP[TIEMPO_PARA_HOSPITALIZACION] (solicitud a asignación) está en minutos, a diferencia de la del día, que está en horas; no se usa en visuales.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
