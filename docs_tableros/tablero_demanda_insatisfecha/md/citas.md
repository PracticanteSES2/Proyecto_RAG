---
tablero: DEMANDA INSATISFECHA
pagina: CITAS
nombre_funcional: Citas canceladas por causas institucionales
bloque: Histórico
tablas: [CITAS MEDICAS]
actualizado: 2026-10-28
version: 2
---

# CITAS

## Propósito
Analiza las citas ambulatorias (consulta médica e imágenes) canceladas por causas de la institución: total, promedio mensual, evolución por mes y distribución por causa y por asegurador. Es de análisis histórico; se llega desde el botón AMBULATORIO de CONSOLIDADO. Página oculta en Power BI (solo CONSOLIDADO es visible).

## Fuentes de datos
- **CITAS MEDICAS**: Citas médicas (CMNCITMED) con fecha de cita desde el 1 de enero de 2025 hasta hoy, estado CCMESTADO = 1 y causa de cancelación (CMNCAUCAN) 2, 3, 4, 5, 20, 25, 26, 27, 28 o 29. Trae la cita, la descripción de la causa (CCCDESCRI), la especialidad, el asegurador y la agrupación ESPE.

## Indicadores
- **Citas canceladas**: Número de citas canceladas. DAX: DISTINCTCOUNT('CITAS MEDICAS'[OID]).
- **Promedio mensual**: Citas canceladas del año en curso divididas por el número del mes actual. Medida PROM_CITAS: DIVIDE(CALCULATE(DISTINCTCOUNT('CITAS MEDICAS'[OID]), YEAR('CITAS MEDICAS'[FECHA]) = YEAR(TODAY())), MONTH(TODAY())).

## Visuales
- **Tarjetas**: CITAS CANCELADAS y PROMEDIO MENSUAL.
- **Gráfico de columnas por mes**: Titulado «CITAS CANCELADAS por Mes»; cantidad mensual de citas canceladas.
- **Gráfico circular por causa**: Titulado «CITAS CANCELADAS por CAUSA»; participación de cada causa (daño de equipo, error en habilitación, mantenimiento de equipo, falta de insumos, calamidad del especialista, entre otras).
- **Gráfico de barras por asegurador**: Titulado «CITAS CANCELADAS por ASEGURADOR»; cantidad de cancelaciones por asegurador.
- **Filtros**: Segmentadores «Date Año» y «Date Mes» (CALENDARIO[Date]), «ESPECIALIDAD» (CITAS MEDICAS[GEEDESCRI]), «TERNOMCOM» (asegurador, TERCEROS[TERNOMCOM]) y «ESPE» (IMAGENES o CONSULTA MÉDICA AMBULATORIA); botón de inicio que vuelve a CONSOLIDADO.

## Reglas de negocio
- **Agrupación ESPE**: Las especialidades con OID 1, 2, 3, 4, 6, 9, 67, 88, 89 y 129 se agrupan como IMAGENES; las demás como CONSULTA MÉDICA AMBULATORIA.
- **Causas incluidas**: Solo cuentan las causas de cancelación 2, 3, 4, 5, 20, 25, 26, 27, 28 y 29, consideradas atribuibles a la institución. La lista de códigos con su nombre está por confirmar.
- **Filtro de página**: Solo cuentan citas con causa CALAMIDAD DEL ESPECIALISTA, DAÑO DE EQUIPO, ERROR EN HABILITACION DE AGENDA, FALTA DE INSUMOS o MANTENIMIENTO DE EQUIPO (CITAS MEDICAS[CCCDESCRI])

## Observaciones
- **Promedio en blanco**: En la captura de la documentación PROMEDIO MENSUAL aparece «(En blanco)»; ocurre cuando no hay citas canceladas en el año en curso.
- **Estado de la cita**: Por confirmar qué significa CCMESTADO = 1 en citas con causa de cancelación.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
