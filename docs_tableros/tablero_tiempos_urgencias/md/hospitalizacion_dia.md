---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: HOSPITALIZACION DIA
nombre_funcional: Oportunidad en la hospitalización del día
bloque: Día
tablas: [ESPERA_HOSPITALIZACION, HOSPITALIZACION_DIA]
actualizado: 2026-10-20
version: 1
---

# HOSPITALIZACION DIA

## Propósito
Muestra la oportunidad en la asignación de cama para los pacientes de urgencias que requieren hospitalización: los que esperan cama, los que están en remisión a otra institución y los que recibieron cama hoy. Todos los tiempos de la página están en horas. Se llega desde el botón de hospitalización de RESUMEN_D y el botón superior izquierdo regresa a RESUMEN_D.

## Fuentes de datos
- **ESPERA_HOSPITALIZACION**: Solicitudes de hospitalización activas de pacientes que ocupan una cama de urgencias, sin límite de fecha; tabla en DirectQuery.
- **HOSPITALIZACION_DIA**: Solicitudes de hospitalización del área de urgencias con cama asignada hoy; tabla en DirectQuery.

## Indicadores
- **Tiempo en espera de hospitalización**: Horas desde la solicitud de hospitalización (SsFechaC) hasta la hora actual. Columna ESPERA_HOSPITALIZACION[TIEMPO_PARA_HOSPITALIZACION].
- **Tiempo para hospitalización**: Horas entre la solicitud de hospitalización y la asignación de cama (FecAsigCama). Columna HOSPITALIZACION_DIA[TIEMPO_PARA_HOSPITALIZACION].

## Visuales
- **Leyenda de oportunidad**: Texto con los rangos del semáforo: 0-4 horas, 5-6 horas y 7 horas o más.
- **Tabla en espera hospitalización**: Columnas DOCUMENTO, PACIENTE y TIEMPO ESPERA. Filtro: pacientes que no están en remisión.
- **Tabla pacientes en remisión**: Mismas columnas que la de espera. Filtro: pacientes con remisión registrada.
- **Tabla pacientes hospitalizados**: Columnas DOCUMENTO, PACIENTE, HORA_SOLICITUD, HORA_ASIGNACION y TIEMPO ESPERA. Su filtro sobre CONSULTAS_DIA no tiene efecto.

## Reglas de negocio
- **Semáforo de hospitalización**: En las tablas de espera y de remisión, verde de 0 a 4 horas, amarillo de 5 a 6 y rojo de 7 o más.
- **Semáforo de hospitalizados**: Verde de 0 a 4 horas, amarillo de 5 a menos de 6 y rojo de 7 o más.
- **Solicitud en espera**: Solicitud de categoría 188 y servicio 1 en estado 1, 2 o 3, de un paciente cuya estancia actual (sin salida) está en una cama del subgrupo 16 (urgencias).
- **Paciente en remisión**: Su ingreso tiene registro en PLANILLAUSUARIO.Con_RemisionMaestro_new; se muestra aparte y no en la lista de espera.
- **Pacientes hospitalizados**: Solicitudes del área de urgencias con fecha de asignación de cama igual a hoy.
- **Horas con DATEDIFF**: Las horas cuentan cambios de hora; 1 hora y 59 minutos se muestran como 1.

## Observaciones
- **Hueco en el semáforo de hospitalizados**: En la tabla de hospitalizados el valor de 6 horas queda sin color.
- **Estados de la solicitud**: Los estados 1, 2 y 3 se interpretan como solicitudes activas. Por confirmar su significado.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
