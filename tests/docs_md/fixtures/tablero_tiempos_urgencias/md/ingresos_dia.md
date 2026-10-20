---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: INGRESOS DIA
nombre_funcional: Oportunidad en el ingreso por enfermería del día
bloque: Día
tablas: [EN ESPERA INGRESO, INGRESOS_DIA]
actualizado: 2026-10-20
version: 1
---

# INGRESOS DIA

## Propósito
Muestra la oportunidad del ingreso por enfermería, es decir, del momento en que el paciente ya valorado en consulta ocupa una cama o espacio del servicio e inicia tratamiento. A la izquierda están los pacientes que esperan ese ingreso y a la derecha los que ya ingresaron hoy, con semáforo. En el histórico este tiempo se llama inicio de tratamiento (INICIO TRATAMIENTO HISTORICOS). Se llega desde el botón de ingreso de RESUMEN_D y el botón superior izquierdo regresa a RESUMEN_D.

## Fuentes de datos
- **EN ESPERA INGRESO**: Ingresos de hoy con consulta en urgencias, sin cama asignada y sin egreso; tabla en DirectQuery.
- **INGRESOS_DIA**: Ingresos del día de la última actualización con consulta en urgencias e ingreso por enfermería, sin egreso; tabla en Import.

## Indicadores
- **Tiempo en espera de ingreso**: Minutos desde el primer folio de hoy (consulta) hasta la hora actual, para pacientes sin cama. Columna EN ESPERA INGRESO[TIEMPO_INGRESO].
- **Tiempo para ingreso por enfermería**: Minutos entre el primer folio del día (consulta) y el inicio de la estancia (HESFECING). Columna INGRESOS_DIA[TIEMPO_INGRESO].

## Visuales
- **Leyenda de oportunidad**: Texto con los rangos del semáforo: 0-30 minutos, 31-60 minutos y 61 minutos o más.
- **Tabla en espera ingreso por enfermería**: Columnas DOCUMENTO, PACIENTE y TIEMPO_ESPERA.
- **Tabla ingresos por enfermería**: Columnas DOCUMENTO, PACIENTE, HORA_CONSULTA, HORA_INGRESO y TIEMPO PARA INGRESO. Su filtro sobre CONSULTAS_DIA[HORA_CONSULTA] no tiene efecto.

## Reglas de negocio
- **Semáforo de ingreso**: En ambas tablas, verde de 0 a 30 minutos, amarillo de 31 a 60 y rojo de 61 o más.
- **Pacientes considerados**: Ingresos con admisión de hoy, con un folio de hoy en el área de urgencias (área 2) y sin egreso.
- **Espera e ingreso**: El paciente espera mientras su estancia no tiene cama asignada (HPNDEFCAM vacío); ingresa cuando la estancia tiene fecha de inicio (HESFECING).
- **Consulta de referencia**: La consulta es el primer folio del día del ingreso.

## Observaciones
- **INGRESOS_DIA en Import**: La lista de espera se actualiza al momento, pero la de ingresos solo con la actualización del conjunto de datos. Por confirmar.
- **Columna TIEMPO_ESPERA sin sentido**: EN ESPERA INGRESO[TIEMPO_ESPERA] calcula DATEDIFF(HORA_INGRESO, TODAY(), MINUTE), que no es un tiempo de espera; no se usa en visuales y se sugiere eliminarla.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
