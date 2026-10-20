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
Muestra la oportunidad del egreso de urgencias: a la izquierda los pacientes con indicación médica de salida que todavía no tienen orden de salida y a la derecha los egresos del día con su tiempo para egreso. Sirve para identificar demoras en el cierre del proceso asistencial y liberar camas. Se llega desde el botón de egreso de RESUMEN_D.

## Fuentes de datos
- **ESPERA_EGRESO**: Folios de urgencias con indicación médica de salida y sin orden de salida; tabla en DirectQuery.
- **EGRESOS_DIA**: Órdenes de salida de hoy en la unidad de urgencias con el último folio del ingreso; tabla en DirectQuery.

## Indicadores
- **Tiempo de espera para egreso**: Minutos desde el folio con la indicación de salida hasta el momento en que se consulta la página. Columna ESPERA_EGRESO[TIEMPO_PARA_EGRESO].
- **Tiempo para egreso**: Minutos entre el último folio de historia clínica y la orden de salida. Columna EGRESOS_DIA[TIEMPO_EGRESO_OK].

## Visuales
- **Leyenda de oportunidad**: Texto en la parte superior con los rangos del semáforo de la página.
- **Tabla en espera egreso**: Pacientes con indicación de salida con documento, nombre y tiempo de espera en minutos. Filtro del visual: menos de 361 minutos.
- **Tabla egresos**: Titulada «EGRESOS»; pacientes con orden de salida hoy con hora del último folio, hora de salida y tiempo para egreso en minutos. Filtro del visual: tiempo mayor que 0 y menor que 361 minutos.
- **Botón regresar**: Botón de la esquina superior izquierda que regresa a RESUMEN_D.

## Reglas de negocio
- **Semáforo de egresos**: Verde de 0 a 60 minutos, amarillo de 61 a 90 y rojo de 91 o más; naranja para valores negativos.
- **Semáforo en espera de egreso**: Verde por debajo de 60 minutos, amarillo de 61 a menos de 90 y rojo de 91 o más.
- **Egresos del día**: Órdenes de salida de hoy no anuladas (SRAORDANU = 0), de ingresos con AINURGCON = 0 y de camas de la unidad 16 (URGENCIAS).
- **Paciente en espera de egreso**: Folio del área de urgencias con indicación médica de tipo 5 o 6 y médico registrado, de pacientes del censo de urgencias. La tabla no tiene filtro de fecha.
- **Límite de la tabla de egresos**: La tabla muestra solo tiempos entre 1 y 360 minutos; el indicador de RESUMEN_D acepta de 1 a 720 minutos.

## Observaciones
- **Huecos en el semáforo de espera**: Los valores exactos de 60 y 90 minutos quedan sin color en la tabla en espera egreso.
- **Tipos de indicación 5 y 6**: Se interpretan como indicaciones de salida o alta. Por confirmar.
- **Límites distintos**: La tabla y el indicador del resumen usan límites distintos (360 y 720 minutos). Por confirmar cuál es el criterio oficial.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
