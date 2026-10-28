---
tablero: TABLERO ANTIBIOTICOS
pagina: DICCIONARIO
nombre_funcional: Diccionario de variables del tablero
bloque: Diccionario
tablas: [ANTIBIOTICOS, Calendario]
actualizado: 2026-10-28
version: 1
---

# DICCIONARIO

## Propósito
Diccionario de variables del tablero TABLERO ANTIBIOTICOS: qué es cada tabla, medida y columna clave del modelo «TABLERO ANTIBIOTICOS», con su cálculo y dónde se usa. Se genera del modelo y de los visuales; las descripciones de negocio marcadas «Por confirmar» las completa quien conoce el tablero.

## Tablas
- **ANTIBIOTICOS**: Aplicaciones de medicamentos del grupo de inventario 36 (antibióticos) registradas en la hoja de enfermería (HCNCONMED) para pacientes que hoy ocupan una cama, con paciente, documento, cama, servicio, asegurador, ingreso, médico, antibiótico, fecha de…. Origen: consulta SQL sobre DGEMPRES10.DBO.HPNDEFCAM, DGEMPRES10.DBO.HPNSUBGRU, DGEMPRES10.DBO.ADNINGRESO, DGEMPRES10.DBO.GENPACIEN, DGEMPRES10.DBO.GENDETCON en la base DWSES (Import). Granularidad: Por confirmar. Columnas principales: ANTIBIOTICO, MEDICO, PACIENTE, SERVICIO, Suspension, ASEGURADOR, CAMA, CONTEODOSIS y 8 más.
- **Calendario**: Por confirmar. Origen: tabla calculada con DAX `CALENDAR("2023-01-01",TODAY())` (Import). Granularidad: Por confirmar. Columnas principales: Date.

## Medidas
- **[Dias Suministrados]**: Días suministrados. Días distintos con aplicación del antibiótico. Unidad: Por confirmar. Tabla: ANTIBIOTICOS. Cálculo: `DISTINCTCOUNT( ANTIBIOTICOS[HORA_APLICACION] )`. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE».
- **[Dosis_Diaria]**: Por confirmar. Unidad: Por confirmar. Tabla: ANTIBIOTICOS. Cálculo: `VAR TotalDosis = SUM(ANTIBIOTICOS[HCCANTIDAD]) VAR Dias = DISTINCTCOUNT(ANTIBIOTICOS[HORA_APLICACION]) RETURN IF( TotalDosis > 0 && Dias > 0, DIVIDE(TotalDosis, Dias), BLANK() )`. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE».
- **[Fecha Fin]**: Fecha fin. Última fecha de aplicación del antibiótico en el contexto. Unidad: fecha. Tabla: ANTIBIOTICOS. Cálculo: `MAX( ANTIBIOTICOS[HORA_APLICACION] )`. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE».
- **[Fecha Inicio]**: Fecha inicio. Primera fecha de aplicación del antibiótico en el contexto. Unidad: fecha. Tabla: ANTIBIOTICOS. Cálculo: `MIN( ANTIBIOTICOS[HORA_APLICACION])`. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE».
- **[PAC_ACT]**: Pacientes activos. Pacientes distintos con algún antibiótico en estado ACTIVO. Unidad: Por confirmar. Tabla: ANTIBIOTICOS. Cálculo: `CALCULATE( DISTINCTCOUNT(ANTIBIOTICOS[DOCUMENTO]), ANTIBIOTICOS[Suspension] = "ACTIVO" )`. Se usa en: ANTIBIOTICOS › Tarjeta «PACIENTE ACTIVOS»; MONITOREO_ANTIBIOTICO › Gráfico de barras «PACIENTES ACTIVOS POR TIPO DE ANTIBIÓTICO»; MONITOREO_ANTIBIOTICO › Gráfico de anillos «PACIENTES ACTIVOS POR SERVICIO»; MONITOREO_ANTIBIOTICO › Tarjeta «PACIENTES ACTIVOS».
- **[TOTAL DOSIS SUMINISTRADAS]**: Por confirmar. Unidad: Por confirmar. Tabla: ANTIBIOTICOS. Cálculo: `SUM(ANTIBIOTICOS[HCCANTIDAD])`. Se usa en: ANTIBIOTICOS › Tarjeta «TOTAL DOSIS SUMINISTRADAS»; MONITOREO_ANTIBIOTICO › Tarjeta «TOTAL DOSIS SUMINISTRADAS».
- **[PAC_SumaMeses]**: Por confirmar. Unidad: Por confirmar. Tabla: ANTIBIOTICOS. Cálculo: `SUMX( VALUES('Calendario'[Date].[Año]), DISTINCTCOUNT(ANTIBIOTICOS[DOCUMENTO]) )`. Se usa en: no aparece en visuales ni filtros del informe.

## Columnas clave
- **ANTIBIOTICOS[ANTIBIOTICO]**: Producto del grupo de inventario con IGRCODIGO = 36; se muestra su descripción corta (IPRDESCOR). Tipo: texto. Valores: Por confirmar. Se usa en: ANTIBIOTICOS › Segmentación de ANTIBIOTICOS[ANTIBIOTICO]; ANTIBIOTICOS › Tabla «PACIENTE»; MONITOREO_ANTIBIOTICO › Segmentación de ANTIBIOTICOS[ANTIBIOTICO]; MONITOREO_ANTIBIOTICO › Gráfico de barras «PACIENTES ACTIVOS POR TIPO DE ANTIBIÓTICO».
- **ANTIBIOTICOS[MEDICO]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE».
- **ANTIBIOTICOS[PACIENTE]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE».
- **ANTIBIOTICOS[SERVICIO]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: ANTIBIOTICOS › Segmentación de ANTIBIOTICOS[SERVICIO]; ANTIBIOTICOS › Tabla «PACIENTE»; MONITOREO_ANTIBIOTICO › Segmentación de ANTIBIOTICOS[SERVICIO]; MONITOREO_ANTIBIOTICO › Gráfico de anillos «PACIENTES ACTIVOS POR SERVICIO».
- **ANTIBIOTICOS[Suspension]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE»; las medidas [PAC_ACT].
- **Calendario[Date]**: Por confirmar. Tipo: fecha. Se usa en: ANTIBIOTICOS › Segmentación de Calendario[Date] (Año); ANTIBIOTICOS › Segmentación de Calendario[Date] (Mes); MONITOREO_ANTIBIOTICO › Segmentación de Calendario[Date] (Año); MONITOREO_ANTIBIOTICO › Segmentación de Calendario[Date] (Mes); las medidas [PAC_SumaMeses].

## Relaciones
- **ANTIBIOTICOS[HORA_APLICACION] → Calendario[Date]**: Muchos a uno, Calendario filtra a ANTIBIOTICOS, activa.

## Historial de cambios
- **2026-10-28 · v1**: Esqueleto generado desde data/model_metadata/tablero_antibioticos y hechos del PBIP.
