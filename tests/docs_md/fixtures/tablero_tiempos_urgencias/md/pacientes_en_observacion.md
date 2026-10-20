---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: PACIENTES EN OBSERVACION
nombre_funcional: Pacientes en observación del día
bloque: Día
tablas: [EN_OBSERVACION, PACIENTES_OBSERVADOS]
actualizado: 2026-10-20
version: 1
---

# PACIENTES EN OBSERVACION

## Propósito
Muestra la permanencia en observación: a la izquierda los pacientes que siguen en observación y cuánto llevan, y a la derecha los que ingresaron hoy y ya terminaron la observación, con hora de inicio, hora de salida y duración, con semáforo. Sirve para detectar estancias prolongadas y apoyar la rotación de camas. Se llega desde el botón de observación de RESUMEN_D y el botón superior izquierdo regresa a RESUMEN_D.

## Fuentes de datos
- **EN_OBSERVACION**: Pacientes con ingreso en los últimos 10 días que siguen en observación; tabla en DirectQuery.
- **PACIENTES_OBSERVADOS**: Pacientes con ingreso hoy que terminaron la observación; tabla en DirectQuery.

## Indicadores
- **Tiempo en observación actual**: Minutos desde el inicio de la estancia (HESFECING) hasta la hora actual, para pacientes que siguen en observación. Columna EN_OBSERVACION[TIEMPO_OBSERVACION].
- **Tiempo en observación**: Minutos entre el inicio de la estancia y el fin de la observación. Columna PACIENTES_OBSERVADOS[TIEMPO_OBSERVACION].

## Visuales
- **Leyenda de oportunidad**: Texto con los rangos del semáforo: 0-240 minutos, 240-360 minutos y 361 minutos o más.
- **Tabla pacientes en observación**: Columnas DOCUMENTO, PACIENTE y TIEMPO EN OBSERVACIÓN. Filtro: sin hora de fin de observación.
- **Tabla pacientes observados**: Columnas DOCUMENTO, PACIENTE, HORA INGRESO (inicio de la estancia), HORA SALIDA (fin de la observación) y TIEMPO EN OBSERVACIÓN. Sus filtros sobre TRIAGES_DIA no tienen efecto.

## Reglas de negocio
- **Semáforo de observación**: En ambas tablas, verde de 0 a 240 minutos (4 horas), amarillo de más de 240 hasta 360 (6 horas) y rojo de más de 360.
- **Fin de la observación**: Es la fecha de la solicitud de hospitalización si el paciente no tiene egreso, o la fecha de egreso si no hay solicitud de hospitalización.
- **Pacientes en observación**: Ingresos de los últimos 10 días con folio en urgencias, estancia iniciada, sin fin de observación y sin egreso.
- **Pacientes observados**: Ingresos de hoy con folio de hoy en urgencias, estancia iniciada y fin de observación definido.

## Observaciones
- **Leyenda con 240 repetido**: La leyenda dice 0-240 y 240-360; según la regla de color, 240 minutos es verde.
- **Ventana de 10 días**: La versión 1 documentaba solo ingresos del día para los pacientes en observación; el modelo trae los últimos 10 días.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
