---
tablero: TABLERO NAOS
pagina: DICCIONARIO
nombre_funcional: Diccionario de variables del tablero
bloque: Diccionario
tablas: [CIRUGÍAS PENDIENTES, ENCUESTAS, Encuestas_Pivot, EXAMENES, GESTION_CLINICA, PACIENTES, ResumenExamenes]
actualizado: 2026-10-28
version: 1
---

# DICCIONARIO

## Propósito
Diccionario de variables del tablero TABLERO NAOS: qué es cada tabla, medida y columna clave del modelo «TABLERO NAOS», con su cálculo y dónde se usa. Se genera del modelo y de los visuales; las descripciones de negocio marcadas «Por confirmar» las completa quien conoce el tablero.

## Tablas
- **CIRUGÍAS PENDIENTES**: Por confirmar. Origen: consulta SQL sobre PLANILLAUSUARIO.DBO.Qx_Procedimiento, PLANILLAUSUARIO.DBO.Qx_ProcedimientoCirugia, PLANILLAUSUARIO.DBO.Qx_SolicitudProgramacion, DGempres10.DBO.GENPACIEN, DGempres10.DBO.GENESPECI en la base DWSES (DirectQuery). Granularidad: Por confirmar. Columnas principales: DOCUMENTO, EPS, ESPECIALIDAD, FechaRegistro, NOMBRE, Oid, PROCEDIMIENTO, TIPO_PACIENTE y 3 más.
- **ENCUESTAS**: Por confirmar. Origen: consulta SQL sobre planillausuario.dbo.Ec_Urgencias, planillausuario.dbo.Preguntas, planillausuario.dbo.Parametros, planillausuario.dbo.Ws_DetalleEnvioSMS, dgempres10.dbo.genareser en la base DWSES (Import). Granularidad: Por confirmar. Columnas principales: FECHA, fechaRegistro, GASNOMBRE, GDENOMBRE, GPANOMCOM, HSUNOMBRE, Observacion, oid y 8 más.
- **Encuestas_Pivot**: Por confirmar. Origen: tabla calculada con DAX `SUMMARIZE ( 'ENCUESTAS', 'ENCUESTAS'[oidingreso], "Calificacion", MAXX ( FILTER ('ENCUESTAS', 'ENCUESTAS'[oidingreso] = EARLIER('ENCUESTAS'…` (Import). Granularidad: Por confirmar. Columnas principales: Calificacion, Observacion, oidingreso.
- **EXAMENES**: Por confirmar. Origen: consulta SQL sobre EXAMENES_NAOS en la base DWSES (DirectQuery). Granularidad: Por confirmar. Columnas principales: AINCONSEC, ESTADO_EXAMEN, GPANOMCOM, HCACODIGO, HSUNOMBRE, PACNUMDOC, SIPDESCUP.
- **GESTION_CLINICA**: Por confirmar. Origen: consulta SQL sobre PLANILLAUSUARIO.DBO.DNSOLISERVICIO_NEW, PLANILLAUSUARIO.DBO.DNCATSERVICIO_NEW, PLANILLAUSUARIO.DBO.DNHISTORIALSS_NEW, PLANILLAUSUARIO.DBO.USUARIO, DGEMPRES10.DBO.ADNINGRESO en la base DWSES (DirectQuery). Granularidad: Por confirmar. Columnas principales: AINCONSEC, CATEGORIA_SOLICITUD, DOCUMENTO_PACIENTE, GPANOMCOM, HSSFECHA, ULT_SEG, APELLIDOS_USUARIO, EPS y 14 más.
- **PACIENTES**: Vista TABLERO_NAOS cargada completa; un registro por paciente con servicio, cama, aseguradora, clasificación, días de estancia y marcas de solicitud de cama, dieta y gestión clínica pendientes. Origen: consulta SQL sobre TABLERO_NAOS en la base DWSES (DirectQuery). Granularidad: Por confirmar. Columnas principales: ADNINGRESO, AINACUDIE, AINCONSEC, AINTELACU, DIETAS_PENDIENTES, EDAD, GDENOMBRE, GPANOMCOM y 17 más.
- **ResumenExamenes**: Por confirmar. Origen: tabla calculada con DAX `SUMMARIZECOLUMNS( EXAMENES[AINCONSEC], EXAMENES[GPANOMCOM], EXAMENES[HCACODIGO], EXAMENES[HSUNOMBRE], "ExamenesPendientes", CONCATENATEX( F…` (Import). Granularidad: Por confirmar. Columnas principales: AINCONSEC, ExamenesPendientes, GPANOMCOM, HSUNOMBRE, HCACODIGO.

## Columnas calculadas
- **PACIENTES[PENDIENTES_GESTION]**: Por confirmar. Tipo: texto. Cálculo: `IF(NOT ISBLANK(PACIENTES[OID_GESTION]),"PENDIENTE SOLICITUD GESTION CLINICA",BLANK())`. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[ColorFila]**: Por confirmar. Tipo: texto. Cálculo: `SWITCH( TRUE(), PACIENTES[DIAS_ESTANCIA]>=6 && PACIENTES[DIAS_ESTANCIA]<=8, "#F2FF82", PACIENTES[DIAS_ESTANCIA]>=9 && PACIENTES[DIAS_ESTANCIA]<=14, "#FFB982", PACIENTES[DIAS_ESTANCIA]>=15, "#FF8F82", PACIENTES[SOLICITUD_CAMA] = "SOLICITUD DE CAMA PENDIENTE", "#ADD8E6", PACIENTES[PENDIENTES_GESTION] = "PENDIENTE SOLICITUD GESTION CLINICA", "#90EE90", PACIENTES[DIETAS_PENDIENTES] = "PENDIENTE DIETA", "#C8A2C8", BLANK() )`. Se usa en: no aparece en visuales ni filtros del informe.

## Columnas clave
- **CIRUGÍAS PENDIENTES[DOCUMENTO]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **CIRUGÍAS PENDIENTES[EPS]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: CIRUGÍAS PENDIENTES › Segmentación de CIRUGÍAS PENDIENTES[EPS]; CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **CIRUGÍAS PENDIENTES[ESPECIALIDAD]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: CIRUGÍAS PENDIENTES › Segmentación de CIRUGÍAS PENDIENTES[ESPECIALIDAD]; CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **CIRUGÍAS PENDIENTES[FechaRegistro]**: Por confirmar. Tipo: fecha. Se usa en: CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **CIRUGÍAS PENDIENTES[NOMBRE]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **CIRUGÍAS PENDIENTES[Oid]**: Por confirmar. Tipo: entero. Se usa en: CIRUGÍAS PENDIENTES › Tarjeta «CIRUGÍAS PENDIENTES».
- **CIRUGÍAS PENDIENTES[PROCEDIMIENTO]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **CIRUGÍAS PENDIENTES[TIPO_PACIENTE]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: CIRUGÍAS PENDIENTES › Segmentación de CIRUGÍAS PENDIENTES[TIPO_PACIENTE]; CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **GESTION_CLINICA[AINCONSEC]**: Por confirmar. Tipo: entero. Se usa en: GESTION CLINICA › Tabla «PACIENTE».
- **GESTION_CLINICA[CATEGORIA_SOLICITUD]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: GESTION CLINICA › Segmentación de GESTION_CLINICA[CATEGORIA_SOLICITUD]; GESTION CLINICA › Tabla «PACIENTE».
- **GESTION_CLINICA[DOCUMENTO_PACIENTE]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: GESTION CLINICA › Tabla «PACIENTE».
- **GESTION_CLINICA[GPANOMCOM]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: GESTION CLINICA › Tabla «PACIENTE».
- **GESTION_CLINICA[HSSFECHA]**: Por confirmar. Tipo: fecha. Se usa en: GESTION CLINICA › Tabla «PACIENTE».
- **GESTION_CLINICA[ULT_SEG]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: GESTION CLINICA › Tabla «PACIENTE».
- **PACIENTES[ADNINGRESO]**: Por confirmar. Tipo: entero. Se usa en: LISTADO › Gráfico circular «SERVICIO»; LISTADO › Gráfico circular «CLASIFICACIÓN».
- **PACIENTES[AINACUDIE]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[AINCONSEC]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: LISTADO › Tarjeta «PACIENTES»; LISTADO › Tabla «PACIENTE»; EXAMENES › Segmentación de PACIENTES[AINCONSEC]; GESTION CLINICA › Segmentación de PACIENTES[AINCONSEC].
- **PACIENTES[AINTELACU]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[DIETAS_PENDIENTES]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[EDAD]**: Por confirmar. Tipo: entero. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[GDENOMBRE]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[GPANOMCOM]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[HCACODIGO]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[HSUNOMBRE]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: LISTADO › Filtro de la página; LISTADO › Segmentación de PACIENTES[HSUNOMBRE]; LISTADO › Tabla «PACIENTE»; LISTADO › Gráfico circular «SERVICIO»; EXAMENES › Filtro de la página; GESTION CLINICA › Segmentación de PACIENTES[HSUNOMBRE] y 1 más.
- **PACIENTES[PACNUMDOC]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[SOLICITUD_CAMA]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[TIPO_PACIENTE]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: LISTADO › Segmentación de PACIENTES[TIPO_PACIENTE]; LISTADO › Tabla «PACIENTE»; LISTADO › Gráfico circular «CLASIFICACIÓN»; GESTION CLINICA › Segmentación de PACIENTES[TIPO_PACIENTE].
- **ResumenExamenes[AINCONSEC]**: Por confirmar. Tipo: entero. Se usa en: EXAMENES › Tabla «INGRESO».
- **ResumenExamenes[ExamenesPendientes]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: EXAMENES › Tabla «INGRESO».
- **ResumenExamenes[GPANOMCOM]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: EXAMENES › Tabla «INGRESO».
- **ResumenExamenes[HSUNOMBRE]**: Por confirmar. Tipo: texto. Valores: Por confirmar. Se usa en: EXAMENES › Segmentación de ResumenExamenes[HSUNOMBRE].

## Relaciones
- **PACIENTES[AINCONSEC] → ResumenExamenes[AINCONSEC]**: Muchos a uno, filtro en ambos sentidos entre PACIENTES y ResumenExamenes, activa.
- **EXAMENES[AINCONSEC] → ResumenExamenes[AINCONSEC]**: Muchos a uno, ResumenExamenes filtra a EXAMENES, inactiva.
- **PACIENTES[AINCONSEC] → EXAMENES[AINCONSEC]**: Muchos a muchos, filtro en ambos sentidos entre PACIENTES y EXAMENES, inactiva.
- **PACIENTES[AINCONSEC] → GESTION_CLINICA[AINCONSEC]**: Muchos a muchos, filtro en ambos sentidos entre PACIENTES y GESTION_CLINICA, activa.

## Historial de cambios
- **2026-10-28 · v1**: Esqueleto generado desde data/model_metadata/tablero_naos y hechos del PBIP.
