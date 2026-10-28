---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: CONSULTAS PRIORITARIAS
nombre_funcional: Consultas prioritarias atendidas por mes
bloque: Histórico
tablas: [CONSULTAS PRIORITARIAS, Calendario, EGRESOS_POR_SERVICIO]
actualizado: 2026-10-20
version: 1
---

# CONSULTAS PRIORITARIAS

## Propósito
Muestra cuántas consultas prioritarias (citas de atención prioritaria efectivamente atendidas) hay cada mes y compara los años. Se llega con el botón CONSULTAS PRIORITARIAS de la página URGENCIAS. Página oculta en modo lectura.

## Fuentes de datos
- **CONSULTAS PRIORITARIAS**: Citas médicas desde 2024-01-01 hasta el último día del mes anterior cuyo tipo de atención contiene «PRIORI», no canceladas y con folio de historia clínica el mismo día; trae asegurador, especialidad, médico, fecha de la cita, tipo de atención y estado. Se une al Calendario por FECHA.

## Indicadores
- **Consultas prioritarias del año en curso**: Cálculo: AÑO_ACTUAL = CALCULATE(COUNT('CONSULTAS PRIORITARIAS'[IDENTIFICACION]), YEAR('CONSULTAS PRIORITARIAS'[FECHA]) = YEAR(TODAY())).
- **Promedio mensual**: Consultas del año en curso divididas entre el número del mes actual. Cálculo: PROMEDIO_MENSUAL = DIVIDE([AÑO_ACTUAL], MONTH(TODAY())).
- **Consultas por mes**: El gráfico cuenta filas con asegurador (Count de ASEGURADOR) y la tabla cuenta IDENTIFICACION.

## Visuales
- **Segmentadores**: ASEGURADOR (columna EGRESOS_POR_SERVICIO[TERNOMCOM]), Año y Mes.
- **Gráfico de consultas por mes**: Líneas tituladas «PACIENTES OBSERVADOS POR MES» que muestran las consultas prioritarias por mes, una línea por año.
- **Tabla de detalle anual**: Matriz de consultas por año (filas) y mes (columnas); excluye 2023 y el año vacío.
- **Tarjetas de consultas**: «TOTAL CONSULTAS PRIORITARIAS» y «PROMEDIO MENSUAL» (PROMEDIO_MENSUAL).
- **Botón de regreso**: Flecha que vuelve a la página anterior.

## Reglas de negocio
- **Consulta prioritaria**: Cita con tipo de atención que contiene «PRIORI», estado distinto de cancelada y con folio el mismo día del mismo médico o especialidad.
- **Mes en curso excluido**: Solo entran citas anteriores al primer día del mes actual.
- **Especialidades excluidas**: No entran las especialidades con identificador 1, 2, 3, 4, 6, 8, 51, 65, 88, 90 y 129 (nombres por confirmar).
- **Agrupación de especialidades**: Hematología, cuidado paliativo, geriatría (incluye medicina interna y geriatría) y neumología se agrupan por nombre; espirometría, difusión con monóxido de carbono y rehabilitación pulmonar van a REHABILITACION PULMONAR; test de caminata y rehabilitación cardiaca a REHABILITACION CARDIACA.

## Observaciones
- **Título equivocado**: El gráfico se titula «PACIENTES OBSERVADOS POR MES» aunque muestra consultas prioritarias.
- **Segmentador sin efecto**: ASEGURADOR usa la columna de EGRESOS_POR_SERVICIO, que no se relaciona con esta tabla; por confirmar si filtra algo.
- **Filtros sobrantes**: La página tiene filtros ocultos sobre OBSERVADOS[MENORES] y OBSERVADOS[fecha] y el gráfico uno sobre CONSULTA_URGENCIAS[FECHA_FOLIO], copiados de otras páginas.
- **Tarjetas en blanco**: En la captura las dos tarjetas muestran «(En blanco)» aunque el gráfico tiene datos del año. Causa por confirmar.
- **Conteos distintos**: El gráfico cuenta ASEGURADOR y la tabla IDENTIFICACION; las filas sin asegurador no aparecen en el gráfico.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
