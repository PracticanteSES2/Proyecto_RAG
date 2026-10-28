---
tablero: TABLERO EPS
pagina: TRIAGES ATENDIDOS
nombre_funcional: Resumen de atenciones, capacidad y ocupación de urgencias
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE, CONSULTA_URGENCIAS, CONSULTAS_PRIORITARIAS, PACIENTES_OBSERVADOS, PACIENTES_HOSPITALIZADOS, %OCUPACIONAL, Calendario]
actualizado: 2026-10-28
version: 2
---

# TRIAGES ATENDIDOS

## Propósito
Página principal del tablero. En pantalla lleva el título «CONSOLIDADO DE ATENCIONES DE URGENCIAS». Resume en tarjetas el volumen de atención de urgencias (triages, consultas de urgencias y prioritarias) y la carga del servicio (observados, hospitalizados y ocupación) para el periodo y la aseguradora elegidos. Es histórica: con los filtros en «Todas» suma desde 2022. Desde aquí se navega a las páginas de detalle.

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: Triages desde el 2022-01-01 hasta hoy, sin la clasificación UA; alimenta las tarjetas de triages atendidos y Triages Gineco.
- **CONSULTA_URGENCIAS**: Triages con ingreso de urgencias; alimenta la tarjeta Consultas urgencias.
- **CONSULTAS_PRIORITARIAS**: Citas de consulta prioritaria desde el 2022-01-01 (ver página CONSULTAS PRIORITARIAS).
- **PACIENTES_OBSERVADOS y PACIENTES_HOSPITALIZADOS**: Ingresos de las áreas de servicio 2 y 42 desde 2022-01-01, de tipo 1 los observados y de tipo 2 los hospitalizados.
- **%OCUPACIONAL**: Ocupación diaria de camas desde 2023-01-01 hasta ayer.

## Indicadores
- **Triages atendidos**: Cantidad de triages realizados en el periodo. Unidad: triages. COUNT de OPORTUNIDAD_TRIAGE[OID_TRIAGE] sin los triages obstétricos ni MUERTO.
- **Triages Gineco**: Cantidad de triages obstétricos. Unidad: triages. COUNT de OPORTUNIDAD_TRIAGE[OID_TRIAGE] solo con DESCRI_TRIGE obstétrico (EMERGENCIA, URGENCIA MEDICA, URGENCIA, NO URGENTE o CONSULTA EXTERNA OBSTETRICA).
- **Consultas urgencias**: Consultas médicas de urgencias de pacientes con triage I, II o III. Unidad: consultas. DISTINCTCOUNT de CONSULTA_URGENCIAS[OID_TRIAGE] sin triages IV, V, obstétricos ni MUERTO.
- **Consultas prioritarias**: Citas prioritarias confirmadas. Unidad: consultas. COUNT de CONSULTAS_PRIORITARIAS[PACNUMDOC] con ESTADO_NOMBRE = CONFIRMADO.
- **Pacientes Observados**: Ingresos de observación en urgencias. Unidad: pacientes. COUNT de PACIENTES_OBSERVADOS[HCENTRIAGE].
- **Pacientes hospitalizados**: Ingresos hospitalizados desde urgencias. Unidad: pacientes. COUNT de PACIENTES_HOSPITALIZADOS[PACNUMDOC] con GASNOMBRE = URGENCIAS.
- **Ocupación de urgencias**: Porcentaje de camas-día ocupadas sobre las disponibles. Unidad: porcentaje. Medida [%OCUPACIONALC] con SERVICIO URGENCIAS o SEXTO PISO y sin camas cuyo código contiene EXP.

## Visuales
- **Filtros de segmentación**: Listas desplegables de Año, Mes y Día (segmentadores «Fecha Año», «Fecha Mes» y «Fecha Día» de Calendario[Fecha]), ASEGURADORA y MENORES DE EDAD (grupo de edad).
- **Tarjetas de atención**: Primera fila con Triages atendidos, Triages Gineco, Consultas urgencias (rótulo «Triages 1 - 2 - 3») y Consultas prioritarias (rótulo «Triages 4 - 5»).
- **Tarjetas de capacidad**: Segunda fila con Pacientes Observados, Pacientes hospitalizados y Ocupación de urgencias (en porcentaje).
- **Botones de navegación**: %ATENCIONES lleva a %ATENCIONES/ADMISIONES; MAPA DE CALOR TRIAGES lleva a la matriz de triages por hora; DETALLE CONSULTAS PRIORITARIAS lleva a CONSULTAS PRIORITARIAS.
- **Elementos de diseño**: Título CONSOLIDADO DE ATENCIONES DE URGENCIAS, logos y recuadros.

## Reglas de negocio
- **Separación por nivel de triage**: Los triages I, II y III se cuentan como consultas de urgencias; las consultas prioritarias vienen de las citas, no de los triages IV y V.
- **Triages obstétricos**: Los códigos con sufijo G se separan de Triages atendidos y se cuentan solo en Triages Gineco.
- **Periodo por defecto**: Sin filtros, las tarjetas acumulan todo el periodo cargado, desde el 2022-01-01 hasta hoy; la ocupación llega hasta ayer.

## Observaciones
- **Rótulo de consultas prioritarias**: La tarjeta dice «Triages 4 - 5» pero cuenta citas prioritarias confirmadas de CITAS_MEDICAS.
- **Ocupación de urgencias**: Incluye el servicio SEXTO PISO y excluye camas con EXP en el código. Por confirmar el motivo.
- **Tipos de ingreso**: Por confirmar que el tipo 1 sea observación y el 2 hospitalización.
- **Tarjeta de triages atendidos**: En la captura su valor coincide con el total del mapa de calor de triages, lo que indica la misma fuente.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
