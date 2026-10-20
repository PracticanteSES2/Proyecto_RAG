---
tablero: TABLERO EPS
pagina: CONSOLIDADO DE ATENCIONES DE URGENCIAS
nombre_funcional: Resumen de atenciones, capacidad y ocupación de urgencias
bloque: Histórico
tablas: [ATENCIONES_ADMISIONES, CONSULTAS_PRIORITARIAS]
actualizado: 2026-10-20
version: 1
---

# CONSOLIDADO DE ATENCIONES DE URGENCIAS

## Propósito
Página principal del tablero. Resume en tarjetas el volumen de atención de urgencias (triages, consultas de urgencias y prioritarias) y la carga del servicio (observados, hospitalizados y ocupación) para el periodo y la aseguradora elegidos. Es histórica: con los filtros en «Todas» suma desde 2022. Desde aquí se navega a las páginas de detalle.

## Fuentes de datos
- **Triages**: Consulta de triages desde el 2022-01-01 (ver General); alimenta la tarjeta de triages atendidos.
- **Consultas prioritarias**: Citas de consulta prioritaria desde el 2022-01-01 (ver página CONSULTAS PRIORITARIAS).
- **Observación, hospitalización y ocupación**: Origen no documentado. Por confirmar.

## Indicadores
- **Triages atendidos**: Cantidad de triages realizados en el periodo, sin la clasificación UA. Unidad: triages. Cálculo por confirmar (conteo de registros de la consulta de triages).
- **Triages Gineco**: Cantidad de triages obstétricos o ginecológicos. Unidad: triages. Cálculo por confirmar.
- **Consultas urgencias**: Consultas médicas de urgencias de pacientes con triage 1, 2 o 3. Unidad: consultas. Cálculo por confirmar.
- **Consultas prioritarias**: Consultas prioritarias de pacientes con triage 4 o 5. Unidad: consultas. Cálculo por confirmar.
- **Pacientes Observados**: Pacientes que pasaron a observación en urgencias. Unidad: pacientes. Cálculo por confirmar.
- **Pacientes hospitalizados**: Pacientes de urgencias que fueron hospitalizados. Unidad: pacientes. Cálculo por confirmar.
- **Ocupación de urgencias**: Porcentaje de ocupación del servicio de urgencias. Unidad: porcentaje. Cálculo por confirmar.

## Visuales
- **Filtros de segmentación**: Listas desplegables de Año, Mes, Día, ASEGURADORA y MENORES DE EDAD (grupo de edad).
- **Tarjetas de atención**: Primera fila con Triages atendidos, Triages Gineco, Consultas urgencias (rótulo «Triages 1 - 2 - 3») y Consultas prioritarias (rótulo «Triages 4 - 5»).
- **Tarjetas de capacidad**: Segunda fila con Pacientes Observados, Pacientes hospitalizados y Ocupación de urgencias (en porcentaje).
- **Botones de navegación**: %ATENCIONES lleva a % ATENCIONES / ADMISIONES; MAPA DE CALOR TRIAGES lleva a la matriz de triages por hora; DETALLE CONSULTAS PRIORITARIAS lleva a CONSULTAS PRIORITARIAS.

## Reglas de negocio
- **Separación por nivel de triage**: Los triages 1, 2 y 3 se cuentan como consultas de urgencias y los triages 4 y 5 como consultas prioritarias.
- **Periodo por defecto**: Sin filtros, las tarjetas acumulan todo el periodo cargado, desde el 2022-01-01 hasta hoy.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Tarjeta de consultas prioritarias**: En la captura su valor coincide con las consultas en estado CONFIRMADO de la página de detalle; por confirmar si la tarjeta filtra solo confirmadas.
- **Tarjeta de triages atendidos**: En la captura su valor coincide con el total del mapa de calor de triages, lo que indica la misma fuente.
- **Fuentes no documentadas**: Las tarjetas de Triages Gineco, Consultas urgencias, Observados, Hospitalizados y Ocupación no tienen consulta ni medida en la documentación. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
