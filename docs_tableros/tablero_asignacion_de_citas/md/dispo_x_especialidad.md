---
tablero: ASIGNACION DE CITAS
pagina: DISPO X ESPECIALIDAD
nombre_funcional: Disponibilidad de agenda de especialistas
bloque: Histórico
tablas: [AGENDA_ESPECIALISTAS, ESPECIALIDADES, EN_ESPERA, CITAS_ASIGNADAS, Calendario]
actualizado: 2026-10-20
version: 1
---

# DISPO X ESPECIALIDAD

## Propósito
Compara, por especialidad y por médico, la agenda abierta en cupos, las citas asignadas, la agenda que queda disponible y las solicitudes en espera. Sirve para ver la carga y la capacidad libre de cada especialidad. La documentación la llama «Disponibilidad de especialistas»; se llega desde el botón DISPONIBILIDAD ESPECIALISTAS de INICIO. Incluye agenda futura hasta 60 días (bloque Histórico).

## Fuentes de datos
- **AGENDA_ESPECIALISTAS**: Bloques de agenda por médico y día con minutos abiertos, citas y cupos; solo citas en estado 0 o 2 y una lista fija de códigos de médico.
- **EN_ESPERA**: Solicitudes en espera por especialidad.
- **CITAS_ASIGNADAS**: Citas asignadas para el gráfico de anillo.
- **ESPECIALIDADES**: Nombre de la especialidad para las filas y el filtro.

## Indicadores
- **Agenda**: Cupos que caben en la agenda abierta. SUM(AGENDA_ESPECIALISTAS[Disponibilidad_Dia]); minutos del bloque divididos por la duración de consulta del médico.
- **Citas asignadas en agenda**: Citas en estado 0 o 2 dentro de la agenda. SUM(AGENDA_ESPECIALISTAS[CANTIDAD_CITAS]).
- **Agenda disponible**: Cupos que quedan libres. SUM(AGENDA_ESPECIALISTAS[Citas_Restantes]); minutos del bloque menos minutos ya asignados, divididos por la duración de consulta.
- **Citas en espera**: Solicitudes en espera de la especialidad. SUM(EN_ESPERA[PENDIENTES]).
- **Asignadas del anillo**: Citas asignadas sin anuladas ni inasistidas. DISTINCTCOUNT(CITAS_ASIGNADAS[OID_CITA]) con CCMESTADO distinto de 1 y 3.

## Visuales
- **Filtros de la página**: Segmentadores de año, mes y día de Calendario y de especialidad (ESPECIALIDADES[GEEDESCRI]).
- **Tabla de disponibilidad**: Matriz con especialidad y, al expandir, MEDICO; columnas AGENDA, CITAS EN ESPERA, CITAS ASIGNADAS y AGENDA DISPONIBLE, con total.
- **Anillo de agenda**: Titulado «EN ESPERA, ASIGNADAS y AGENDA DISPONIBLE»; conteo y porcentaje de solicitudes en espera, citas asignadas y cupos disponibles.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Duración de consulta**: Es la mayor duración de las citas del médico en esa especialidad durante el último mes, contando solo citas de hasta 45 minutos; si no hay dato se usan 30 minutos.
- **Filas con agenda**: La matriz oculta filas sin valor de agenda (Disponibilidad_Dia vacía).
- **Fechas de la agenda**: Bloques de agenda desde 2024-04-01 hasta 60 días después de hoy, filtrados por la fecha del bloque.

## Observaciones
- **Agenda disponible negativa**: Cuando se asignan más minutos que los abiertos (sobrecupo) la agenda disponible queda negativa.
- **En espera no se reparte por médico**: CITAS EN ESPERA no tiene relación con el médico; en las filas de médico repite el valor de la especialidad.
- **Regla de 60 minutos sin efecto**: El SQL intenta usar 60 minutos para el código de médico 4300, pero la condición de 30 minutos se evalúa antes y siempre gana.
- **Agenda sin citas**: La consulta parte de las citas, así que un bloque de agenda sin ninguna cita no aparece. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
