---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: TIEMPOS TRIAGE DIA
nombre_funcional: Oportunidad en la atención de triage del día
bloque: Día
tablas: [EN ESPERA TRIAGE, TRIAGES_DIA]
actualizado: 2026-10-20
version: 1
---

# TIEMPOS TRIAGE DIA

## Propósito
Muestra en tiempo real la oportunidad del triage: a la izquierda los turnos del digiturno que esperan triage y cuánto llevan, y a la derecha los pacientes clasificados hoy con la hora del turno, la hora del triage y la espera, con semáforo. Se llega desde el botón de triage de RESUMEN_D y el botón superior izquierdo regresa a RESUMEN_D.

## Fuentes de datos
- **EN ESPERA TRIAGE**: Turnos del digiturno pendientes de triage, sin límite de fecha; tabla en DirectQuery.
- **TRIAGES_DIA**: Triages registrados hoy, excepto el código UA; tabla en DirectQuery.

## Indicadores
- **Tiempo en espera de triage**: Minutos desde la toma del turno hasta la hora actual, para turnos sin triage. Columna EN ESPERA TRIAGE[TIEMPO_MAX_ESPERA_PAC].
- **Tiempo de espera para triage**: Minutos entre la toma del turno (hora digiturno) y el registro del triage. Columna TRIAGES_DIA[MIN].

## Visuales
- **Leyenda de oportunidad**: Texto con los rangos del semáforo: 0-15 minutos, 16-30 minutos y 31 minutos o más.
- **Tabla en espera triage**: Columnas TURNO, PACIENTE (nombre en el digiturno) y TIEMPO EN ESPERA.
- **Tabla pacientes atendidos en triage**: Columnas DOCUMENTO, NOMBRE, HORA DIGITURNO, HORA TRIAGE y TIEMPO DE ESPERA. Filtros: MIN no vacío (excluye pacientes sin turno) y clasificación distinta de URGENCIA OBSTETRICA (III-G).

## Reglas de negocio
- **Semáforo de triage**: En ambas tablas, verde de 0 a 15 minutos, amarillo de 16 a 30 y rojo de 31 o más.
- **Turno en espera de triage**: Turno con estado 0 en el digiturno (HCCESTADO = 0) y concepto de turno 1 a 7 o 17 (HCNCONCOTRI).
- **Espera sin límite de fecha**: Un turno pendiente de días anteriores sigue en la tabla de espera con su tiempo acumulado hasta que cambie de estado.
- **Nombre del paciente en espera**: Se obtiene cruzando turno y fecha con PLANILLAUSUARIO.AdmisionTriage; si no hay cruce queda vacío.
- **Pacientes atendidos**: Triages con fecha de HCTFECTRI igual a hoy, excepto el código UA.

## Observaciones
- **Turnos sin cerrar**: Los turnos de días anteriores que nunca se cerraron inflan la lista de espera. Por confirmar si debe limitarse a los turnos del día.
- **Significado de los conceptos de turno**: Los conceptos 1 a 7 y 17 de HCNCONCOTRI no están descritos. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
