---
tablero: TABLERO ANTIBIOTICOS
pagina: ANTIBIOTICOS
nombre_funcional: Detalle de pacientes con antibiótico y totales de aplicaciones y pacientes activos
bloque: Día
tablas: [ANTIBIOTICOS]
actualizado: 2026-10-20
version: 1
---

# ANTIBIOTICOS

## Propósito
Página principal del tablero. Muestra el total de dosis suministradas y de pacientes activos, y el listado de cada paciente con el antibiótico, servicio, estado del tratamiento, médico, fecha de inicio, fecha de fin y días suministrados. Sirve para el seguimiento individual de los tratamientos de los pacientes hospitalizados hoy.

## Fuentes de datos
- **ANTIBIOTICOS**: Aplicaciones de antibióticos de los pacientes que ocupan cama, con su estado de tratamiento.

## Indicadores
- **Total dosis suministradas**: Combinaciones distintas de paciente, antibiótico y fecha de aplicación. Medida TOTAL ATB = COUNTROWS(SUMMARIZE(ANTIBIOTICOS, ANTIBIOTICOS[PACIENTE], ANTIBIOTICOS[ANTIBIOTICO], ANTIBIOTICOS[HORA_APLICACION])).
- **Pacientes activos**: Pacientes distintos con algún antibiótico en estado ACTIVO. Medida PAC_ACT = CALCULATE(DISTINCTCOUNT(ANTIBIOTICOS[DOCUMENTO]), ANTIBIOTICOS[Suspension] = "ACTIVO").
- **Fecha inicio**: Primera fecha de aplicación del antibiótico en el contexto. Medida Fecha Inicio = MIN(ANTIBIOTICOS[HORA_APLICACION]).
- **Fecha fin**: Última fecha de aplicación del antibiótico en el contexto. Medida Fecha Fin = MAX(ANTIBIOTICOS[HORA_APLICACION]).
- **Días suministrados**: Días distintos con aplicación del antibiótico. Medida Dias Suministrados = DISTINCTCOUNT(ANTIBIOTICOS[HORA_APLICACION]).

## Visuales
- **Segmentadores**: ANTIBIOTICO, Año, Mes y SERVICIO.
- **Tarjetas**: TOTAL DOSIS SUMINISTRADAS (TOTAL ATB) y PACIENTES ACTIVOS (PAC_ACT).
- **Botón MONITOREO ANTIBIOTICO**: Abre la página MONITOREO ANTIBIOTICO.
- **Tabla de pacientes**: PACIENTE, ANTIBIOTICO, SERVICIO, SUSPENSION (estado del tratamiento), MEDICO, fecha de inicio, fecha de fin y días suministrados.

## Reglas de negocio
- **Año y Mes**: Los segmentadores filtran por la fecha de aplicación; cambian los totales, las fechas de inicio y fin y los días suministrados.

## Observaciones
- **Dosis o días**: TOTAL ATB cuenta una vez cada paciente, antibiótico y día; si un paciente recibe varias dosis el mismo día, cuentan como una. El título «dosis suministradas» puede confundirse con número de dosis.
- **Descripción de días suministrados**: La documentación dice «número de aplicaciones registradas», pero la medida cuenta días distintos con aplicación.
- **Fila por médico**: La tabla incluye el médico, así que un mismo paciente y antibiótico puede aparecer en varias filas, una por médico que registró aplicaciones.
- **Nombre de página**: La documentación no da el nombre de la página; se usa el del tablero. Nombre de página en Power BI por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
