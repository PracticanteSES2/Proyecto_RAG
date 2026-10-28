---
tablero: TABLERO ANTIBIOTICOS
pagina: DICCIONARIO
nombre_funcional: Diccionario de variables del tablero
bloque: Diccionario
tablas: [ANTIBIOTICOS, Calendario]
actualizado: 2026-10-28
version: 2
---

# DICCIONARIO

## Propósito
Diccionario de variables del tablero TABLERO ANTIBIOTICOS: qué es cada tabla, medida y columna clave del modelo «TABLERO ANTIBIOTICOS», con su cálculo y dónde se usa. Se genera del modelo y de los visuales; las descripciones de negocio marcadas «Por confirmar» las completa quien conoce el tablero.

## Tablas
- **ANTIBIOTICOS**: Aplicaciones de antibióticos (medicamentos del grupo de inventario 36) registradas en la hoja de enfermería para pacientes que hoy ocupan una cama, con paciente, documento, cama, servicio, asegurador, ingreso, médico, fecha de aplicación, cantidades y estado del tratamiento (Suspension). Sin filtro de fechas: trae toda la estancia del paciente. Origen: consulta SQL sobre DGEMPRES10.DBO.HPNDEFCAM, DGEMPRES10.DBO.HPNSUBGRU, DGEMPRES10.DBO.ADNINGRESO, DGEMPRES10.DBO.GENPACIEN, DGEMPRES10.DBO.GENDETCON en la base DWSES (Import). Granularidad: una fila por aplicación registrada: paciente, antibiótico, médico, fecha (sin hora), cantidad y observación (SELECT DISTINCT). Dos aplicaciones del mismo día con la misma cantidad, médico y observación se colapsan en una fila. Columnas principales: ANTIBIOTICO, MEDICO, PACIENTE, SERVICIO, Suspension, ASEGURADOR, CAMA, CONTEODOSIS y 8 más.
- **Calendario**: Calendario de fechas, un día por fila, desde 2023-01-01 hasta hoy. Sirve para los segmentadores de año y mes, filtra a ANTIBIOTICOS por la fecha de aplicación. Origen: tabla calculada con DAX `CALENDAR("2023-01-01",TODAY())` (Import). Granularidad: una fila por día. Columnas principales: Date.

## Medidas
- **[Dias Suministrados]**: Días suministrados. Días distintos con aplicación del antibiótico. Unidad: días. Tabla: ANTIBIOTICOS. Cálculo: `DISTINCTCOUNT( ANTIBIOTICOS[HORA_APLICACION] )`. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE».
- **[Dosis_Diaria]**: Promedio de la cantidad aplicada por día con aplicación (total de HCCANTIDAD dividido entre los días distintos); se interpreta como cuánto antibiótico recibe el paciente por día de tratamiento. Queda vacía si no hay cantidad o días. Unidad: unidades de medicamento por día (la unidad de HCCANTIDAD depende de la presentación; Por confirmar) Tabla: ANTIBIOTICOS. Cálculo: `VAR TotalDosis = SUM(ANTIBIOTICOS[HCCANTIDAD]) VAR Dias = DISTINCTCOUNT(ANTIBIOTICOS[HORA_APLICACION]) RETURN IF( TotalDosis > 0 && Dias > 0, DIVIDE(TotalDosis, Dias), BLANK() )`. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE».
- **[Fecha Fin]**: Fecha fin. Última fecha de aplicación del antibiótico en el contexto. Unidad: fecha. Tabla: ANTIBIOTICOS. Cálculo: `MAX( ANTIBIOTICOS[HORA_APLICACION] )`. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE».
- **[Fecha Inicio]**: Fecha inicio. Primera fecha de aplicación del antibiótico en el contexto. Unidad: fecha. Tabla: ANTIBIOTICOS. Cálculo: `MIN( ANTIBIOTICOS[HORA_APLICACION])`. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE».
- **[PAC_ACT]**: Pacientes activos. Pacientes distintos (por documento) con algún antibiótico en estado ACTIVO; es decir, con más unidades despachadas por farmacia que aplicadas en enfermería. Unidad: pacientes. Tabla: ANTIBIOTICOS. Cálculo: `CALCULATE( DISTINCTCOUNT(ANTIBIOTICOS[DOCUMENTO]), ANTIBIOTICOS[Suspension] = "ACTIVO" )`. Se usa en: ANTIBIOTICOS › Tarjeta «PACIENTE ACTIVOS»; MONITOREO_ANTIBIOTICO › Gráfico de barras «PACIENTES ACTIVOS POR TIPO DE ANTIBIÓTICO»; MONITOREO_ANTIBIOTICO › Gráfico de anillos «PACIENTES ACTIVOS POR SERVICIO»; MONITOREO_ANTIBIOTICO › Tarjeta «PACIENTES ACTIVOS».
- **[TOTAL DOSIS SUMINISTRADAS]**: Total de dosis suministradas: suma de la cantidad aplicada (HCCANTIDAD) de las aplicaciones del contexto. No cuenta aplicaciones; suma cantidades. La documentación del propietario describe otra medida (TOTAL ATB, que cuenta combinaciones paciente-antibiótico-día) que no existe en el modelo. Unidad: unidades de medicamento (la unidad de HCCANTIDAD depende de la presentación; Por confirmar) Tabla: ANTIBIOTICOS. Cálculo: `SUM(ANTIBIOTICOS[HCCANTIDAD])`. Se usa en: ANTIBIOTICOS › Tarjeta «TOTAL DOSIS SUMINISTRADAS»; MONITOREO_ANTIBIOTICO › Tarjeta «TOTAL DOSIS SUMINISTRADAS».
- **[PAC_SumaMeses]**: Suma, por año del calendario, de los pacientes distintos (por documento); un paciente con aplicaciones en dos años cuenta dos veces. Medida auxiliar sin uso en visuales ni en la documentación. Unidad: pacientes (sumados por año) Tabla: ANTIBIOTICOS. Cálculo: `SUMX( VALUES('Calendario'[Date].[Año]), DISTINCTCOUNT(ANTIBIOTICOS[DOCUMENTO]) )`. Se usa en: no aparece en visuales ni filtros del informe.

## Columnas clave
- **ANTIBIOTICOS[ANTIBIOTICO]**: Producto del grupo de inventario con IGRCODIGO = 36; se muestra su descripción corta (IPRDESCOR). Tipo: texto. Valores: descripciones cortas de los productos del grupo de inventario 36; la lista exacta depende de los datos. Se usa en: ANTIBIOTICOS › Segmentación de ANTIBIOTICOS[ANTIBIOTICO]; ANTIBIOTICOS › Tabla «PACIENTE»; MONITOREO_ANTIBIOTICO › Segmentación de ANTIBIOTICOS[ANTIBIOTICO]; MONITOREO_ANTIBIOTICO › Gráfico de barras «PACIENTES ACTIVOS POR TIPO DE ANTIBIÓTICO».
- **ANTIBIOTICOS[MEDICO]**: Nombre del médico que registró la aplicación (GMENOMCOM); un mismo paciente y antibiótico puede aparecer en varias filas, una por médico. Tipo: texto. Valores: nombres de médicos; no se documentan aquí. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE».
- **ANTIBIOTICOS[PACIENTE]**: Nombre completo del paciente hospitalizado (GPANOMCOM); identifica al paciente en la tabla de detalle. No se documentan valores. Tipo: texto. Valores: nombres de pacientes; dato personal, no se documenta. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE».
- **ANTIBIOTICOS[SERVICIO]**: Servicio u hospitalización donde está la cama del paciente (nombre del subgrupo de cama, HSUNOMBRE). Tipo: texto. Valores: nombres de servicios hospitalarios; la lista exacta depende de los datos. Se usa en: ANTIBIOTICOS › Segmentación de ANTIBIOTICOS[SERVICIO]; ANTIBIOTICOS › Tabla «PACIENTE»; MONITOREO_ANTIBIOTICO › Segmentación de ANTIBIOTICOS[SERVICIO]; MONITOREO_ANTIBIOTICO › Gráfico de anillos «PACIENTES ACTIVOS POR SERVICIO».
- **ANTIBIOTICOS[Suspension]**: Estado del tratamiento con el antibiótico, calculado en la consulta SQL. SUSPENDIDO si la orden tiene marca de suspensión (HCSREGSUS = 1); ACTIVO si lo despachado por farmacia supera lo aplicado; FINALIZADO en los demás casos. Tipo: texto. Valores: SUSPENDIDO, ACTIVO, FINALIZADO. Se usa en: ANTIBIOTICOS › Tabla «PACIENTE»; las medidas [PAC_ACT].
- **Calendario[Date]**: Fecha del calendario; se relaciona con la fecha de aplicación (ANTIBIOTICOS[HORA_APLICACION]) y alimenta los segmentadores de año y mes. Tipo: fecha. Se usa en: ANTIBIOTICOS › Segmentación de Calendario[Date] (Año); ANTIBIOTICOS › Segmentación de Calendario[Date] (Mes); MONITOREO_ANTIBIOTICO › Segmentación de Calendario[Date] (Año); MONITOREO_ANTIBIOTICO › Segmentación de Calendario[Date] (Mes); las medidas [PAC_SumaMeses].
- **ANTIBIOTICOS[DOCUMENTO]**: Número de documento del paciente (PACNUMDOC); la medida [PAC_ACT] lo cuenta distinto para contar pacientes. Tipo: texto. Valores: dato personal, no se documenta. Se usa en: las medidas [PAC_ACT], [PAC_SumaMeses].
- **ANTIBIOTICOS[HORA_APLICACION]**: Fecha de la aplicación (se castea a fecha desde la hora de registro hcrhorreg, así que no guarda la hora pese al nombre). Tipo: fecha. Se usa en: las medidas [Dias Suministrados], [Fecha Fin], [Fecha Inicio], [Dosis_Diaria]; relación con Calendario[Date].
- **ANTIBIOTICOS[HCCANTIDAD]**: Cantidad de medicamento registrada en cada aplicación en la hoja de enfermería (HCNCONMED). Tipo: decimal. Se usa en: las medidas [TOTAL DOSIS SUMINISTRADAS], [Dosis_Diaria].
- **ANTIBIOTICOS[CONTEODOSIS]**: Número de aplicaciones registradas de ese antibiótico (orden) en el ingreso, con respuesta HCRESPUES = 0; se repite en todas las filas de la misma orden. Tipo: entero. Se usa en: ningún visual del informe.
- **ANTIBIOTICOS[SUMADOSIS]**: Suma de las cantidades aplicadas de esa orden en el ingreso; es la base del estado Suspension (se compara con lo despachado). Tipo: decimal. Se usa en: ningún visual del informe.
- **ANTIBIOTICOS[dias]**: Días distintos con aplicación de esa orden en el ingreso, calculado en la consulta SQL. Tipo: entero. Se usa en: ningún visual del informe; la tabla usa la medida [Dias Suministrados].
- **ANTIBIOTICOS[ASEGURADOR]**: Nombre del tercero asegurador del contrato del ingreso (TERNOMCOM). Tipo: texto. Valores: nombres de aseguradores; la lista exacta depende de los datos. Se usa en: ningún visual del informe.
- **ANTIBIOTICOS[CAMA]**: Código de la cama (HCACODIGO) que ocupa el paciente. Tipo: texto. Se usa en: ningún visual del informe.
- **ANTIBIOTICOS[INGRESO]**: Consecutivo del ingreso del paciente (AINCONSEC). Tipo: entero. Se usa en: ningún visual del informe.
- **ANTIBIOTICOS[hcobserva]**: Observación en texto libre de la aplicación; puede contener información clínica, no se documenta. Tipo: texto. Se usa en: ningún visual del informe.
- **ANTIBIOTICOS[hccantdosis]**: Cantidad de dosis del registro de la aplicación (HCCANTDOSIS); su significado exacto es Por confirmar. Tipo: decimal. Se usa en: ningún visual del informe.

## Relaciones
- **ANTIBIOTICOS[HORA_APLICACION] → Calendario[Date]**: Muchos a uno, Calendario filtra a ANTIBIOTICOS, activa. Hace que los segmentadores de año y mes filtren por la fecha de aplicación.

## Observaciones
- **Pendiente para el dueño**: Por confirmar: unidad de HCCANTIDAD y de HCCANTDOSIS; significado de HCAESTADO <> 6 y HCRESPUES = 0; si el título «dosis suministradas» debe sumar cantidades o contar aplicaciones.
- **Medida distinta de la documentación**: La documentación describe TOTAL ATB (COUNTROWS de SUMMARIZE por paciente, antibiótico y fecha) pero las tarjetas usan [TOTAL DOSIS SUMINISTRADAS] = SUM(HCCANTIDAD); [TOTAL ATB] no existe en el modelo.
- **Posible subconteo**: La consulta usa SELECT DISTINCT y la fecha sin hora; aplicaciones repetidas el mismo día con igual cantidad, médico y observación se colapsan y SUM(HCCANTIDAD) puede quedar por debajo del real.
- **Estado por despacho**: Suspension ACTIVO se infiere de la diferencia entre unidades despachadas (HCSCANDESP) y aplicadas, no de una orden médica vigente.
- **Medidas sin uso**: [PAC_SumaMeses] no aparece en ningún visual ni en la documentación; [Dosis_Diaria] sí se usa en la tabla pero la documentación no la describe.
- **Calendario automático**: La tabla LocalDateTable y DateTableTemplate son calendarios automáticos de Power BI para Calendario[Date]; no tienen contenido de negocio.

## Historial de cambios
- **2026-10-28 · v1**: Esqueleto generado desde data/model_metadata/tablero_antibioticos y hechos del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
