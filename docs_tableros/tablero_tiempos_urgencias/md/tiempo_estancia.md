---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: TIEMPO ESTANCIA
nombre_funcional: Tiempo total en urgencias, histórico
bloque: Histórico
tablas: [TIEMPO_URGENCIAS, TIEMPO_HOSPI]
actualizado: 2026-10-20
version: 1
---

# TIEMPO ESTANCIA

## Propósito
Muestra la permanencia de los pacientes en urgencias, en horas: el tiempo total desde la admisión hasta la orden de salida y el de los pacientes que se hospitalizan, desde la admisión hasta el cierre de la solicitud de hospitalización. En la versión 1 se llamaba «Tiempo total en urgencias». Se llega desde RESUMEN.

## Fuentes de datos
- **TIEMPO_URGENCIAS**: Órdenes de salida no anuladas desde el 01/01/2024 de pacientes de la unidad URGENCIAS (unidad 16); FECHA es la fecha de la orden de salida; tabla en Import.
- **TIEMPO_HOSPI**: Solicitudes de hospitalización (categoría 188, servicio 1) de ingresos desde el 01/01/2024; FECHA es la fecha de admisión; tabla en Import.

## Indicadores
- **Tiempo promedio de estancia en urgencias**: Horas entre la admisión y la orden de salida. AVERAGE(TIEMPO_URGENCIAS[TiempoMinutosSalidaUrgencias]).
- **Tiempo promedio en urgencias de hospitalizados**: Horas entre la admisión y el cierre de la solicitud de hospitalización (SsFechaFin). AVERAGE(TIEMPO_HOSPI[TIEMPO_HOSPI]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran cada tabla por su propia FECHA.
- **Tarjetas de estancia**: Tiempo promedio de estancia en urgencias y tiempo promedio en urgencias de pacientes hospitalizados, en horas.
- **Gráfico de líneas por mes**: Dos líneas en horas por año y mes: TIEMPO EN URGENCIAS y TIEMPO EN URGENCIAS PACIENTES HOSPITALIZADOS.
- **Botón de regreso**: Lleva a RESUMEN.

## Reglas de negocio
- **Fechas distintas por tabla**: El tiempo total se ubica en el mes de la orden de salida; el de hospitalizados, en el mes de la admisión.

## Observaciones
- **Estancia con historia en facturación**: El tiempo total solo tiene valor cuando facturación recibió la historia antes de la orden de salida y vale 0 si enfermería la entregó después; puede sesgar el promedio. Por confirmar la regla.
- **Horas en columna de minutos**: TiempoMinutosSalidaUrgencias está en horas pese a su nombre.
- **Columna sin uso**: TIEMPO_URGENCIAS[TIEMPO_HOSPI] (admisión a solicitud de hospitalización, en minutos) no se usa en visuales.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
