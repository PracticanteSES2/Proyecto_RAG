---
tablero: TABLERO ANTIBIOTICOS
pagina: ANTIBIOTICOS
nombre_funcional: Detalle de pacientes con antibiótico y totales de aplicaciones y pacientes activos
bloque: Día
tablas: [ANTIBIOTICOS]
actualizado: 2026-10-28
version: 2
---

# ANTIBIOTICOS

## Propósito
Página principal del tablero. Muestra el total de dosis suministradas y de pacientes activos, y el listado de cada paciente con el antibiótico, servicio, estado del tratamiento, médico, fecha de inicio, fecha de fin y días suministrados. Sirve para el seguimiento individual de los tratamientos de los pacientes hospitalizados hoy.

## Fuentes de datos
- **ANTIBIOTICOS**: Aplicaciones de antibióticos de los pacientes que ocupan cama, con su estado de tratamiento.

## Indicadores
- **Total dosis suministradas**: Suma de la cantidad aplicada (HCCANTIDAD) de las aplicaciones del contexto, en unidades de medicamento. Medida TOTAL DOSIS SUMINISTRADAS = SUM(ANTIBIOTICOS[HCCANTIDAD]).
- **Pacientes activos**: Pacientes distintos (por documento) con algún antibiótico en estado ACTIVO; la tarjeta se rotula PACIENTE ACTIVOS. Medida PAC_ACT = CALCULATE(DISTINCTCOUNT(ANTIBIOTICOS[DOCUMENTO]), ANTIBIOTICOS[Suspension] = "ACTIVO").
- **Fecha inicio**: Primera fecha de aplicación del antibiótico en el contexto. Medida Fecha Inicio = MIN(ANTIBIOTICOS[HORA_APLICACION]).
- **Fecha fin**: Última fecha de aplicación del antibiótico en el contexto. Medida Fecha Fin = MAX(ANTIBIOTICOS[HORA_APLICACION]).
- **Días suministrados**: Días distintos con aplicación del antibiótico. Medida Dias Suministrados = DISTINCTCOUNT(ANTIBIOTICOS[HORA_APLICACION]).
- **Dosis diaria**: Cantidad promedio aplicada por día con aplicación, en unidades de medicamento por día. Medida Dosis_Diaria = DIVIDE(SUM(HCCANTIDAD), DISTINCTCOUNT(HORA_APLICACION)); vacía si no hay cantidad o días.

## Visuales
- **Segmentadores**: ANTIBIOTICO, Date Año y Date Mes1 (año y mes de Calendario[Date], la fecha de aplicación) y SERVICIO.
- **Tarjetas**: TOTAL DOSIS SUMINISTRADAS (suma de HCCANTIDAD) y PACIENTE ACTIVOS (PAC_ACT).
- **Botón MONITOREO ANTIBIOTICO**: Abre la página MONITOREO ANTIBIOTICO.
- **Tabla de pacientes**: PACIENTE, ANTIBIOTICO, SERVICIO, SUSPENSION (estado del tratamiento), MEDICO, DOSIS DIARIA, FECHA INICIO, FECHA FIN y DIAS SUMINISTRADOS, ordenada por fecha de inicio de la más reciente a la más antigua. El visual solo muestra los tratamientos con SUSPENSION = ACTIVO.

## Reglas de negocio
- **Año y Mes**: Los segmentadores filtran por la fecha de aplicación; cambian los totales, las fechas de inicio y fin y los días suministrados.
- **Tabla solo de activos**: La tabla de pacientes filtra ANTIBIOTICOS[Suspension] = «ACTIVO»; los tratamientos suspendidos o finalizados no aparecen en ella, aunque las tarjetas TOTAL DOSIS SUMINISTRADAS sí los incluyen.

## Observaciones
- **Dosis o días**: TOTAL DOSIS SUMINISTRADAS suma cantidades (HCCANTIDAD), no cuenta aplicaciones; la documentación del propietario describe TOTAL ATB, que cuenta combinaciones distintas de paciente, antibiótico y día, pero esa medida no existe en el modelo.
- **Descripción de días suministrados**: La documentación dice «número de aplicaciones registradas», pero la medida cuenta días distintos con aplicación.
- **Fila por médico**: La tabla incluye el médico, así que un mismo paciente y antibiótico puede aparecer en varias filas, una por médico que registró aplicaciones.
- **Nombre de página**: La página se llama ANTIBIOTICOS en Power BI; es la página visible del informe.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
