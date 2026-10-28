---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: RESUMEN
nombre_funcional: Datos históricos: resumen (inicio del bloque histórico)
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE, CONSULTA_URGENCIAS, TIEMPO_PARA_EGRESO, TIEMPO_URGENCIAS, TIEMPO_HOSPI]
actualizado: 2026-10-28
version: 2
---

# RESUMEN

## Propósito
Página de inicio del bloque histórico. Resume para el periodo elegido el tiempo para triage, entre triage y admisión, para consulta, para el egreso, el tiempo total en urgencias y el de los pacientes que se hospitalizan, con la evolución mensual de los tres primeros. Desde aquí se navega a la página histórica de cada etapa. Se llega desde RESUMEN_D y el botón superior izquierdo regresa a RESUMEN_D.

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: Triages desde el 01/01/2023, excepto UA; FECHA es la fecha del triage; tabla en Import.
- **CONSULTA_URGENCIAS**: Triages desde el 01/01/2023 con admisión no anulada y su primer folio; FECHA es la fecha de admisión; tabla en Import.
- **TIEMPO_PARA_EGRESO**: Órdenes de salida desde el 01/01/2023 de todas las unidades; FECHA es la fecha de la orden; tabla en Import.
- **TIEMPO_URGENCIAS**: Órdenes de salida desde el 01/01/2024 de pacientes de la unidad URGENCIAS; FECHA es la fecha de la orden; tabla en Import.
- **TIEMPO_HOSPI**: Solicitudes de hospitalización de ingresos desde el 01/01/2024; FECHA es la fecha de admisión; tabla en Import.

## Indicadores
- **Tiempo promedio para atención en triage**: Minutos entre el turno del digiturno y el triage; los triages sin turno no cuentan. AVERAGE(OPORTUNIDAD_TRIAGE[MIN]).
- **Tiempo entre triage y admisión**: Minutos entre el triage y la admisión, sin MUERTO, II-G ni III-G. CALCULATE(AVERAGE(CONSULTA_URGENCIAS[MINUTOS_ADMISION]), NOT CONSULTA_URGENCIAS[TIPO_TRIAGE] IN {"MUERTO", "URGENCIA MEDICA OBSTETRICA - II-G", "URGENCIA OBSTETRICA - III-G"}).
- **Tiempo promedio para atención en consulta**: Minutos entre la admisión y el primer folio, solo triage I a V. CALCULATE(AVERAGE(CONSULTA_URGENCIAS[MINUTOS_CONSULTA]), CONSULTA_URGENCIAS[TIPO_TRIAGE] IN {"I", "II", "III", "IV", "V"}).
- **Tiempo promedio para el egreso**: Minutos entre el último folio y la orden de salida, egresos válidos de urgencias. CALCULATE(AVERAGE(TIEMPO_PARA_EGRESO[TIEMPO_EGRESO_OK]), TIEMPO_PARA_EGRESO[SUBGRUPO] = "URGENCIAS", TIEMPO_PARA_EGRESO[VALIDADOR] <> -1).
- **Tiempo promedio en urgencias (egreso)**: Horas entre la admisión y la orden de salida. AVERAGE(TIEMPO_URGENCIAS[TiempoMinutosSalidaUrgencias]).
- **Tiempo promedio en urgencias (hospitalización)**: Horas entre la admisión y el cierre de la solicitud de hospitalización. AVERAGE(TIEMPO_HOSPI[TIEMPO_HOSPI]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran cada tabla por su propia FECHA.
- **Tarjetas de triage, admisión y consulta**: Los tres primeros indicadores en minutos, con los filtros de tipo de triage indicados.
- **Gráfico de áreas de tiempos por mes**: Por año y mes, promedio en minutos de TIEMPO PARA TRIAGE, TIEMPO PARA ADMISIÓN y TIEMPO PARA ATENCIÓN EN CONSULTA, sin filtro de tipo de triage. Sus filtros sobre TIEMPO_PARA_EGRESO no tienen efecto.
- **Medidor de egreso**: Tiempo promedio para el egreso en minutos; escala de 0 a 60.
- **Tarjetas de tiempo en urgencias**: Tiempo promedio en urgencias del egreso y de la hospitalización, en horas.
- **Botones de navegación**: Llevan a RESUMEN_D (regreso), TIEMPO TRIAGE, TIEMPO TRIAGE-ADMISION, TIEMPO PARA CONSULTA, INICIO TRATAMIENTO HISTORICOS, OBSERVACIÓN HISTORICO, EXAMENES, IMAGENES, INTERCONSULTAS HISTORICO, TIEMPO EGRESO, TIEMPO HOSPI y TIEMPO ESTANCIA.
- **Nombres de campos**: Nombres de los campos en el informe: segmentadores de Calendario[FECHA] «Date Año», «Date Mes».

## Reglas de negocio
- **Fecha de cada tabla**: OPORTUNIDAD_TRIAGE se filtra por fecha del triage, CONSULTA_URGENCIAS y TIEMPO_HOSPI por fecha de admisión, y TIEMPO_PARA_EGRESO y TIEMPO_URGENCIAS por fecha de la orden de salida.
- **Datos desde 2024**: Los indicadores de tiempo en urgencias solo tienen datos desde el 01/01/2024.

## Observaciones
- **Criterios de triage distintos**: Las tarjetas de admisión y de consulta filtran tipos de triage distintos y el gráfico no filtra ninguno; pueden no coincidir. Por confirmar el criterio común.
- **Horas en columna de minutos**: TiempoMinutosSalidaUrgencias está en horas pese a su nombre.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
