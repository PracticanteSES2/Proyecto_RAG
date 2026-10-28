---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: RESUMEN_D
nombre_funcional: Resumen día (página de inicio del tablero)
bloque: Día
tablas: [TRIAGES_DIA, CONSULTAS_DIA, TIEMPO_EGRESO_DIA, HOSPITALIZACION_DIA]
actualizado: 2026-10-28
version: 2
---

# RESUMEN_D

## Propósito
Página de inicio del tablero y única visible en modo lectura. Muestra el recorrido del paciente en urgencias como un diagrama con un botón sobre cada etapa para entrar a su detalle del día y, abajo, cuatro indicadores del día: tiempo para triage, para consulta, para el egreso y para hospitalización. Desde aquí se entra también al bloque histórico.

## Fuentes de datos
- **TRIAGES_DIA**: Triages registrados hoy, excepto el código UA; tabla en DirectQuery.
- **CONSULTAS_DIA**: Triages de hoy con su admisión y su primer folio de historia clínica; tabla en DirectQuery.
- **TIEMPO_EGRESO_DIA**: Órdenes de salida de hoy de todas las unidades; tabla en DirectQuery.
- **HOSPITALIZACION_DIA**: Solicitudes de hospitalización del área de urgencias con cama asignada hoy; tabla en DirectQuery.

## Indicadores
- **Tiempo promedio para triage**: Minutos entre la toma del turno en el digiturno y el registro del triage, para los triages de hoy. AVERAGE(TRIAGES_DIA[TIEMPO_PARA_TRIAGE_DIA]); los pacientes sin turno cuentan con 0 minutos.
- **Tiempo promedio para consulta urgencias**: Minutos entre la admisión y el primer folio de historia clínica, para los triages de hoy. AVERAGE(CONSULTAS_DIA[TIEMPO_CONSULTA]); los pacientes sin folio no cuentan.
- **Tiempo promedio para el egreso**: Minutos entre el último folio y la orden de salida, para órdenes de hoy de la unidad URGENCIAS con tiempo válido. CALCULATE(AVERAGE(TIEMPO_EGRESO_DIA[TIEMPO_EGRESO_OK]), TIEMPO_EGRESO_DIA[SUBGRUPO] = "URGENCIAS", TIEMPO_EGRESO_DIA[VALIDADOR] <> -1).
- **Tiempo promedio para hospitalización**: Horas entre la solicitud de hospitalización y la asignación de cama, para las camas asignadas hoy. AVERAGE(HOSPITALIZACION_DIA[TIEMPO_PARA_HOSPITALIZACION]).
- **Fecha de los datos**: Día al que corresponden los datos mostrados. MAX(TRIAGES_DIA[FECHA]).

## Visuales
- **Diagrama de flujo con botones**: Imagen con las etapas de urgencias y un botón sobre cada una hacia TIEMPOS TRIAGE DIA, ADMISIONES DIA, CONSULTAS DIA, CONSULTAS PRIORITARIAS, INGRESOS DIA, PACIENTES EN OBSERVACION, INTERCONSULTAS DIA, LABORATORIOS, IMAGENES DIA, HOSPITALIZACION DIA y EGRESOS DIA.
- **Botones al histórico**: En la esquina superior derecha, un botón lleva a MAPA DE CALOR TRIAGE y otro a RESUMEN, inicio del bloque histórico.
- **Tarjeta fecha de los datos**: Muestra el máximo de TRIAGES_DIA[FECHA].
- **Tarjeta tiempo para triage**: Promedio de TRIAGES_DIA[TIEMPO_PARA_TRIAGE_DIA] en minutos, sin filtros.
- **Tarjeta tiempo para consulta**: Promedio de CONSULTAS_DIA[TIEMPO_CONSULTA] en minutos. Su filtro (excluye MUERTO, II-G y III-G) está sobre CONSULTA_URGENCIAS, tabla sin relación, y no tiene efecto.
- **Medidor de egreso**: Promedio de TIEMPO_EGRESO_DIA[TIEMPO_EGRESO_OK] en minutos con SUBGRUPO = URGENCIAS y VALIDADOR distinto de -1; escala de 0 a 60.
- **Medidor de hospitalización**: Promedio de HOSPITALIZACION_DIA[TIEMPO_PARA_HOSPITALIZACION] en horas; escala de 0 a 60. Su filtro sobre TIEMPO_PARA_EGRESO[SUBGRUPO] no tiene efecto.
- **Nombres de campos**: Nombres de los campos en el informe: tarjeta «Última fecha: FECHA».

## Reglas de negocio
- **Recálculo en tiempo real**: Los cuatro indicadores se recalculan al abrir o actualizar la página porque sus tablas están en DirectQuery.
- **Egresos válidos en el resumen**: El indicador de egreso solo promedia egresos de la unidad URGENCIAS con tiempo mayor que 0 y hasta 720 minutos.
- **Unidades de la página**: Hospitalización está en horas; triage, consulta y egreso están en minutos.

## Observaciones
- **Pacientes sin turno en el promedio de triage**: La tarjeta cuenta con 0 minutos a los pacientes sin turno, mientras que la tabla de atendidos de TIEMPOS TRIAGE DIA los excluye; el promedio de la tarjeta puede ser menor. Por confirmar el criterio.
- **Escalas de los medidores**: La escala de 0 a 60 del medidor de hospitalización está en horas y la del medidor de egreso en minutos.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
