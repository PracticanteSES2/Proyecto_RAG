---
tablero: BRIEFING HOSPITALARIO
pagina: EGRESOS PROBABLES
nombre_funcional: Pacientes hospitalizados con fecha probable de egreso y egresos efectivos de hoy
bloque: Día
tablas: [EGRESOS PROBABLES, TablaFechas]
actualizado: 2026-10-28
version: 2
---

# EGRESOS PROBABLES

## Propósito
Lista los pacientes hospitalizados con fecha probable de egreso y cuenta cuántos egresaron efectivamente hoy. Sirve para anticipar qué camas quedarán libres y planear las altas. Se llega desde el botón EGRESOS PROBABLES del visual EGRESOS PROBABLES por SERVICIO en INICIO.

## Fuentes de datos
- **EGRESOS PROBABLES**: Tabla FACT_EGRESOS_PROBABLES (servicio, cama, ingreso, paciente y fecha probable de salida) unida con plan, aseguradora, epicrisis y orden de salida. Calcula la fecha de epicrisis, la fecha de orden de salida y la marca EGRESO_EFECTIVO_HOY.
- **TablaFechas**: Calendario para el segmentador de día; la medida TieneDatos limita los días a los que tienen registros.

## Indicadores
- **Egresos probables**: Pacientes con fecha probable de egreso según los filtros. Cálculo por confirmar (conteo de ingresos).
- **Egresos efectivos hoy**: Pacientes con egreso efectivo en la fecha de hoy. Cálculo por confirmar (suma de EGRESO_EFECTIVO_HOY).

## Visuales
- **Tarjetas**: EGRESOS PROBABLES y EGRESOS EFECTIVOS HOY.
- **Segmentadores**: SERVICIO, ASEGURADORA, PLAN DE BENEFICIOS, Año, Mes y Dia.
- **Tabla de egresos probables**: SERVICIO, PACIENTE, CAMA y FECHA PROBABLE DE EGRESO, ordenada por fecha probable de egreso.
- **EGRESOS PROBABLES por SERVICIO**: Anillo con número y porcentaje de egresos probables por servicio.

## Reglas de negocio
- **Egreso efectivo hoy**: EGRESO_EFECTIVO_HOY vale 1 si el ingreso tiene orden de salida con fecha de hoy o epicrisis con fecha de hoy; si tiene ambas, vale 1 solo cuando la epicrisis es de hoy.
- **Fecha probable de egreso**: Es la FechaSalida registrada en FACT_EGRESOS_PROBABLES.

## Observaciones
- **Versión de marzo**: La versión de marzo de 2026 tenía una consulta simple sin epicrisis ni egresos efectivos; se documenta la de septiembre.
- **Caso con epicrisis y orden**: Un paciente con orden de salida de hoy y epicrisis de otro día queda en 0. Por confirmar si es intencional.
- **Nombre de página**: La página se llama EGRESOS PROBABLES en Power BI; está oculta y se llega con el botón DETALLE de su visual en INICIO.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
