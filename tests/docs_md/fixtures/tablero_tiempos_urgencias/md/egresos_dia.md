---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: EGRESOS DIA
nombre_funcional: Oportunidad en los egresos del día
bloque: Día
tablas: [ESPERA_EGRESO, EGRESOS_DIA]
actualizado: 2026-10-20
version: 1
---

# EGRESOS DIA

## Propósito
Muestra la oportunidad del egreso de urgencias: a la izquierda los pacientes con indicación médica de salida que aún no tienen orden de salida y cuánto llevan, y a la derecha los egresos del día con la hora del último folio, la hora de salida y el tiempo para el egreso, con semáforo. Se llega desde el botón de egreso de RESUMEN_D y el botón superior izquierdo regresa a RESUMEN_D.

## Fuentes de datos
- **ESPERA_EGRESO**: Folios del área de urgencias con indicación de salida, de pacientes del censo de urgencias, sin límite de fecha; tabla en DirectQuery.
- **EGRESOS_DIA**: Órdenes de salida de hoy de pacientes de la unidad URGENCIAS; tabla en DirectQuery.

## Indicadores
- **Tiempo en espera de egreso**: Minutos desde el folio con la indicación de salida hasta la hora actual. Columna ESPERA_EGRESO[TIEMPO_PARA_EGRESO].
- **Tiempo para el egreso**: Minutos entre el último folio de historia clínica del ingreso y la orden de salida. Columna EGRESOS_DIA[TIEMPO_EGRESO_OK].

## Visuales
- **Leyenda de oportunidad**: Texto con los rangos del semáforo: 0-60 minutos, 61-90 minutos y 91 minutos o más.
- **Tabla en espera egreso**: Columnas DOCUMENTO, PACIENTE y TIEMPO DE ESPERA. Filtro: menos de 361 minutos.
- **Tabla egresos**: Columnas DOCUMENTO, PACIENTE, HORA FOLIO SALIDA (último folio), HORA SALIDA (orden de salida) y TIEMPO PARA EGRESO. Filtro: tiempo mayor que 0 y menor que 361 minutos; su filtro sobre CONSULTAS_DIA[HORA_CONSULTA] no tiene efecto.

## Reglas de negocio
- **Semáforo de egresos**: En la tabla de egresos, verde de 0 a 60 minutos, amarillo de 61 a 90, rojo de 91 o más y naranja para valores negativos.
- **Semáforo de espera de egreso**: Verde de 0 a menos de 60 minutos, amarillo de 61 a menos de 90 y rojo de 91 o más.
- **Egresos del día**: Órdenes de salida de hoy no anuladas (SRAORDANU = 0), de ingresos con AINURGCON = 0 y de pacientes cuya cama pertenece a la unidad 16 (URGENCIAS).
- **Paciente en espera de egreso**: Folio del área de urgencias con indicación médica de tipo 5 o 6 (HCITIPIND) y médico registrado, de un paciente del censo de urgencias (PLANILLAUSUARIO.Et_ConsultaGrl, servicio 16).
- **Límite de 6 horas**: Ambas tablas muestran solo tiempos menores que 361 minutos; el indicador de RESUMEN_D usa el criterio de validez de 1 a 720 minutos.

## Observaciones
- **Huecos en el semáforo de espera**: En la tabla de espera los valores de 60 y 90 minutos quedan sin color.
- **Tipos de indicación 5 y 6**: Se interpretan como indicaciones de salida o alta. Por confirmar.
- **Espera sin excluir egresados**: La lista de espera no excluye pacientes que ya tienen egreso (esas condiciones están comentadas en la sentencia SQL); el filtro de 6 horas limita el efecto. Por confirmar.
- **Límites distintos**: La tabla usa 360 minutos y el indicador del resumen 720. Por confirmar cuál es el criterio oficial.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
