---
tablero: TABLERO NAOS
pagina: DICCIONARIO
nombre_funcional: Diccionario de variables del tablero
bloque: Diccionario
tablas: [CIRUGÍAS PENDIENTES, ENCUESTAS, Encuestas_Pivot, EXAMENES, GESTION_CLINICA, PACIENTES, ResumenExamenes]
actualizado: 2026-10-28
version: 2
---

# DICCIONARIO

## Propósito
Diccionario de variables del tablero TABLERO NAOS: qué es cada tabla, columna clave y relación del modelo «TABLERO NAOS», con su cálculo y dónde se usa. El modelo no tiene medidas DAX; las cifras de las tarjetas cuentan filas o valores de las columnas. Las descripciones de columnas de la vista TABLERO_NAOS se deducen de los nombres, de las consultas y de las páginas, porque la vista no está documentada.

## Tablas
- **CIRUGÍAS PENDIENTES**: Solicitudes de cirugía pendientes de pacientes de medicina prepagada, póliza, particular y plan complementario, con procedimientos, especialidad, médico y estado actual. Origen: consulta SQL sobre PLANILLAUSUARIO.DBO.Qx_Procedimiento, PLANILLAUSUARIO.DBO.Qx_ProcedimientoCirugia, PLANILLAUSUARIO.DBO.Qx_SolicitudProgramacion, DGempres10.DBO.GENPACIEN, DGempres10.DBO.GENESPECI en la base DWSES (DirectQuery). Granularidad: una fila por solicitud de programación quirúrgica. Columnas principales: DOCUMENTO, EPS, ESPECIALIDAD, FechaRegistro, NOMBRE, Oid, PROCEDIMIENTO, TIPO_PACIENTE y 3 más.
- **ENCUESTAS**: Respuestas de la encuesta de satisfacción de urgencias (pregunta 1 de calificación y pregunta 2 de observación) con el servicio y el convenio del paciente; ninguna página del informe la usa. Origen: consulta SQL sobre planillausuario.dbo.Ec_Urgencias, planillausuario.dbo.Preguntas, planillausuario.dbo.Parametros, planillausuario.dbo.Ws_DetalleEnvioSMS, dgempres10.dbo.genareser en la base DWSES (Import). Granularidad: una fila por respuesta a una pregunta de la encuesta para un ingreso. Columnas principales: FECHA, fechaRegistro, GASNOMBRE, GDENOMBRE, GPANOMCOM, HSUNOMBRE, Observacion, oid y 8 más.
- **Encuestas_Pivot**: Resumen de ENCUESTAS con una calificación y una observación por ingreso (pregunta 241 para la calificación y 242 para la observación); ninguna página del informe la usa. Origen: tabla calculada con DAX `SUMMARIZE ( 'ENCUESTAS', 'ENCUESTAS'[oidingreso], "Calificacion", MAXX ( FILTER ('ENCUESTAS', 'ENCUESTAS'[oidingreso] = EARLIER('ENCUESTAS'…` (Import). Granularidad: una fila por ingreso (oidingreso). Columnas principales: Calificacion, Observacion, oidingreso.
- **EXAMENES**: Exámenes y estudios diagnósticos de los pacientes del tablero con su estado; los pendientes son los de ESTADO_EXAMEN igual a PENDIENTE. Origen: consulta SQL sobre EXAMENES_NAOS en la base DWSES (DirectQuery). Granularidad: una fila por examen de un ingreso. Columnas principales: AINCONSEC, ESTADO_EXAMEN, GPANOMCOM, HCACODIGO, HSUNOMBRE, PACNUMDOC, SIPDESCUP.
- **GESTION_CLINICA**: Trámites de gestión clínica y administrativa abiertos de pacientes hospitalizados, con categoría, último seguimiento, usuario que lo hizo, ingreso, paciente y EPS. Une los convenios 125, 126 y 127 con los ingresos priorizados. Origen: consulta SQL sobre PLANILLAUSUARIO.DBO.DNSOLISERVICIO_NEW, PLANILLAUSUARIO.DBO.DNCATSERVICIO_NEW, PLANILLAUSUARIO.DBO.DNHISTORIALSS_NEW, PLANILLAUSUARIO.DBO.USUARIO, DGEMPRES10.DBO.ADNINGRESO en la base DWSES (DirectQuery). Granularidad: una fila por solicitud de servicio (OID_SOLICITUD). Columnas principales: AINCONSEC, CATEGORIA_SOLICITUD, DOCUMENTO_PACIENTE, GPANOMCOM, HSSFECHA, ULT_SEG, APELLIDOS_USUARIO, EPS y 14 más.
- **PACIENTES**: Vista TABLERO_NAOS cargada completa; un registro por paciente con servicio, cama, aseguradora, clasificación, días de estancia y marcas de solicitud de cama, dieta y gestión clínica pendientes. Origen: consulta SQL sobre TABLERO_NAOS en la base DWSES (DirectQuery). Granularidad: una fila por paciente hospitalizado con pendientes activos. Columnas principales: ADNINGRESO, AINACUDIE, AINCONSEC, AINTELACU, DIETAS_PENDIENTES, EDAD, GDENOMBRE, GPANOMCOM y 17 más.
- **ResumenExamenes**: Lista consolidada de exámenes pendientes por ingreso, separados por coma, calculada desde EXAMENES. Origen: tabla calculada con DAX `SUMMARIZECOLUMNS( EXAMENES[AINCONSEC], EXAMENES[GPANOMCOM], EXAMENES[HCACODIGO], EXAMENES[HSUNOMBRE], "ExamenesPendientes", CONCATENATEX( F…` (Import). Granularidad: una fila por ingreso, paciente, cama y servicio. Columnas principales: AINCONSEC, ExamenesPendientes, GPANOMCOM, HSUNOMBRE, HCACODIGO.

## Columnas calculadas
- **PACIENTES[PENDIENTES_GESTION]**: Marca de gestión clínica pendiente: vale «PENDIENTE SOLICITUD GESTION CLINICA» si el paciente tiene OID_GESTION y queda vacía si no. Alimenta el color de fila verde. Tipo: texto. Cálculo: `IF(NOT ISBLANK(PACIENTES[OID_GESTION]),"PENDIENTE SOLICITUD GESTION CLINICA",BLANK())`. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[ColorFila]**: Color hexadecimal de cada fila de la tabla de pacientes según estancia y pendientes: amarillo de 6 a 8 días, naranja de 9 a 14, rojo desde 15, azul claro con cama pendiente, verde con gestión clínica pendiente y lila con dieta pendiente. Se aplica como formato condicional de la tabla. Tipo: texto. Cálculo: `SWITCH( TRUE(), PACIENTES[DIAS_ESTANCIA]>=6 && PACIENTES[DIAS_ESTANCIA]<=8, "#F2FF82", PACIENTES[DIAS_ESTANCIA]>=9 && PACIENTES[DIAS_ESTANCIA]<=14, "#FFB982", PACIENTES[DIAS_ESTANCIA]>=15, "#FF8F82", PACIENTES[SOLICITUD_CAMA] = "SOLICITUD DE CAMA PENDIENTE", "#ADD8E6", PACIENTES[PENDIENTES_GESTION] = "PENDIENTE SOLICITUD GESTION CLINICA", "#90EE90", PACIENTES[DIETAS_PENDIENTES] = "PENDIENTE DIETA", "#C8A2C8", BLANK() )`. Se usa en: no aparece en visuales ni filtros del informe.

## Columnas clave
- **CIRUGÍAS PENDIENTES[DOCUMENTO]**: Número de documento del paciente. Tipo: texto. Valores: identificador personal, no se documentan valores. Se usa en: CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **CIRUGÍAS PENDIENTES[EPS]**: Nombre del convenio (EPS o aseguradora) del paciente. Tipo: texto. Valores: nombres de convenios de los tipos MEDICINA PREPAGADA, PÓLIZA, PARTICULAR, PLAN COMPLEMENTARIO (convenios 125, 126, 127 y 122). Se usa en: CIRUGÍAS PENDIENTES › Segmentación de CIRUGÍAS PENDIENTES[EPS]; CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **CIRUGÍAS PENDIENTES[ESPECIALIDAD]**: Especialidad médica de la solicitud de cirugía. Tipo: texto. Valores: descripción de la especialidad del catálogo GENESPECI. Se usa en: CIRUGÍAS PENDIENTES › Segmentación de CIRUGÍAS PENDIENTES[ESPECIALIDAD]; CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **CIRUGÍAS PENDIENTES[FechaRegistro]**: Fecha y hora en que se registró la solicitud de cirugía. Tipo: fecha. Se usa en: CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **CIRUGÍAS PENDIENTES[NOMBRE]**: Nombre completo del paciente. Tipo: texto. Valores: nombres de personas, no se documentan. Se usa en: CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **CIRUGÍAS PENDIENTES[Oid]**: Identificador de la solicitud de cirugía; la tarjeta CIRUGÍAS PENDIENTES lo cuenta. Tipo: entero. Se usa en: CIRUGÍAS PENDIENTES › Tarjeta «CIRUGÍAS PENDIENTES».
- **CIRUGÍAS PENDIENTES[PROCEDIMIENTO]**: Procedimientos de la solicitud unidos en una sola celda y separados por « * »; queda vacío si la solicitud no tiene procedimientos. Tipo: texto. Valores: descripciones de procedimientos quirúrgicos. Se usa en: CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **CIRUGÍAS PENDIENTES[TIPO_PACIENTE]**: Tipo de paciente según el convenio. Tipo: texto. Valores: MEDICINA PREPAGADA, PÓLIZA, PARTICULAR, PLAN COMPLEMENTARIO (convenios 125, 126, 127 y 122). Se usa en: CIRUGÍAS PENDIENTES › Segmentación de CIRUGÍAS PENDIENTES[TIPO_PACIENTE]; CIRUGÍAS PENDIENTES › Tabla «DOCUMENTO».
- **GESTION_CLINICA[AINCONSEC]**: Consecutivo del ingreso hospitalario; une la solicitud con PACIENTES. Tipo: entero. Se usa en: GESTION CLINICA › Tabla «PACIENTE».
- **GESTION_CLINICA[CATEGORIA_SOLICITUD]**: Nombre de la categoría del trámite, en mayúsculas. Tipo: texto. Valores: nombres de las categorías 171, 172, 174, 177, 178, 179, 180, 181, 182, 183, 229, 289, 367, 375, 377, 384 y 404 de DNCATSERVICIO_NEW. Se usa en: GESTION CLINICA › Segmentación de GESTION_CLINICA[CATEGORIA_SOLICITUD]; GESTION CLINICA › Tabla «PACIENTE».
- **GESTION_CLINICA[DOCUMENTO_PACIENTE]**: Número de documento del paciente. Tipo: texto. Valores: identificador personal, no se documentan valores. Se usa en: GESTION CLINICA › Tabla «PACIENTE».
- **GESTION_CLINICA[GPANOMCOM]**: Nombre completo del paciente. Tipo: texto. Valores: nombres de personas, no se documentan. Se usa en: GESTION CLINICA › Tabla «PACIENTE».
- **GESTION_CLINICA[HSSFECHA]**: Fecha del último seguimiento de la solicitud (historial en estado 3); queda vacía si no hay seguimiento. Tipo: fecha. Se usa en: GESTION CLINICA › Tabla «PACIENTE».
- **GESTION_CLINICA[ULT_SEG]**: Texto del último seguimiento; si no hay seguimiento, la descripción original de la solicitud. Tipo: texto. Valores: texto libre. Se usa en: GESTION CLINICA › Tabla «PACIENTE».
- **PACIENTES[ADNINGRESO]**: Identificador del ingreso en la vista TABLERO_NAOS; los gráficos circulares lo cuentan como número de pacientes. Tipo: entero. Se usa en: LISTADO › Gráfico circular «SERVICIO»; LISTADO › Gráfico circular «CLASIFICACIÓN».
- **PACIENTES[AINACUDIE]**: Acudiente (familiar o acompañante) del paciente, por el nombre del campo. Tipo: texto. Valores: nombres de personas, no se documentan. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[AINCONSEC]**: Consecutivo del ingreso hospitalario (columna INGRESO); es la llave de las relaciones con las demás tablas y la tarjeta PACIENTES lo cuenta. Tipo: texto. Valores: número de ingreso guardado como texto. Se usa en: LISTADO › Tarjeta «PACIENTES»; LISTADO › Tabla «PACIENTE»; EXAMENES › Segmentación de PACIENTES[AINCONSEC]; GESTION CLINICA › Segmentación de PACIENTES[AINCONSEC].
- **PACIENTES[AINTELACU]**: Teléfono del acudiente, por el nombre del campo. Tipo: texto. Valores: números telefónicos, no se documentan. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[DIETAS_PENDIENTES]**: Marca de dieta pendiente; vale «PENDIENTE DIETA» cuando el paciente tiene una dieta por atender. Alimenta el color lila. Tipo: texto. Valores: PENDIENTE DIETA o vacío. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[EDAD]**: Edad del paciente en años. Tipo: entero. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[GDENOMBRE]**: Nombre del convenio (EPS o aseguradora) del paciente. Tipo: texto. Valores: nombres de convenios de los tipos MEDICINA PREPAGADA, PÓLIZA, PARTICULAR, PLAN COMPLEMENTARIO (convenios 125, 126, 127 y 122). Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[GPANOMCOM]**: Nombre completo del paciente. Tipo: texto. Valores: nombres de personas, no se documentan. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[HCACODIGO]**: Código de la cama que ocupa el paciente. Tipo: texto. Valores: códigos de cama de la clínica. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[HSUNOMBRE]**: Nombre del servicio hospitalario donde está el paciente; filtra las páginas LISTADO, EXAMENES y GESTION CLINICA. Tipo: texto. Valores: servicios hospitalarios como pisos, cuidado intermedio y atención domiciliaria. Se usa en: LISTADO › Filtro de la página; LISTADO › Segmentación de PACIENTES[HSUNOMBRE]; LISTADO › Tabla «PACIENTE»; LISTADO › Gráfico circular «SERVICIO»; EXAMENES › Filtro de la página; GESTION CLINICA › Segmentación de PACIENTES[HSUNOMBRE] y 1 más.
- **PACIENTES[PACNUMDOC]**: Número de documento del paciente. Tipo: texto. Valores: identificador personal, no se documentan valores. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[SOLICITUD_CAMA]**: Marca de solicitud de cama; vale «SOLICITUD DE CAMA PENDIENTE» cuando hay una solicitud sin atender. Alimenta el color azul claro. Tipo: texto. Valores: SOLICITUD DE CAMA PENDIENTE u otro texto de la vista, por confirmar. Se usa en: LISTADO › Tabla «PACIENTE».
- **PACIENTES[TIPO_PACIENTE]**: Tipo de paciente según el convenio (GDECONFAC); filtra LISTADO y GESTION CLINICA y alimenta el gráfico por clasificación. Tipo: texto. Valores: MEDICINA PREPAGADA, PÓLIZA, PARTICULAR, PLAN COMPLEMENTARIO (convenios 125, 126, 127 y 122). Se usa en: LISTADO › Segmentación de PACIENTES[TIPO_PACIENTE]; LISTADO › Tabla «PACIENTE»; LISTADO › Gráfico circular «CLASIFICACIÓN»; GESTION CLINICA › Segmentación de PACIENTES[TIPO_PACIENTE].
- **ResumenExamenes[AINCONSEC]**: Consecutivo del ingreso; une el resumen con PACIENTES. Tipo: entero. Se usa en: EXAMENES › Tabla «INGRESO».
- **ResumenExamenes[ExamenesPendientes]**: Nombres de los exámenes con estado PENDIENTE del ingreso, separados por coma. Tipo: texto. Valores: lista de exámenes de laboratorio, imágenes, terapias y procedimientos. Se usa en: EXAMENES › Tabla «INGRESO».
- **ResumenExamenes[GPANOMCOM]**: Nombre completo del paciente. Tipo: texto. Valores: nombres de personas, no se documentan. Se usa en: EXAMENES › Tabla «INGRESO».
- **ResumenExamenes[HSUNOMBRE]**: Nombre del servicio del paciente; filtra la página EXAMENES. Tipo: texto. Valores: servicios hospitalarios. Se usa en: EXAMENES › Segmentación de ResumenExamenes[HSUNOMBRE].

## Relaciones
- **PACIENTES[AINCONSEC] → ResumenExamenes[AINCONSEC]**: Muchos a uno, filtro en ambos sentidos entre PACIENTES y ResumenExamenes, activa. Une cada paciente con su lista de exámenes pendientes; en la página EXAMENES el filtro de ResumenExamenes afecta a PACIENTES y viceversa.
- **EXAMENES[AINCONSEC] → ResumenExamenes[AINCONSEC]**: Muchos a uno, ResumenExamenes filtra a EXAMENES, inactiva. Une cada examen con su resumen por ingreso; está inactiva, por lo que no filtra salvo que una medida la active.
- **PACIENTES[AINCONSEC] → EXAMENES[AINCONSEC]**: Muchos a muchos, filtro en ambos sentidos entre PACIENTES y EXAMENES, inactiva. Une pacientes con el detalle de exámenes; está inactiva porque el detalle se consulta por ResumenExamenes.
- **PACIENTES[AINCONSEC] → GESTION_CLINICA[AINCONSEC]**: Muchos a muchos, filtro en ambos sentidos entre PACIENTES y GESTION_CLINICA, activa. Hace que los filtros de servicio y tipo de paciente de PACIENTES lleguen a las solicitudes de GESTION_CLINICA en la página GESTION CLINICA.

## Observaciones
- **Sin medidas**: El modelo no define medidas DAX; las tarjetas cuentan filas o valores de columnas.
- **Tablas sin uso**: ENCUESTAS y Encuestas_Pivot (encuesta de satisfacción de urgencias) no se usan en ninguna página del informe.
- **Consulta de gestión clínica distinta de la documentación**: La consulta excluye solicitudes en estados 4, 12, 5 y 6 (la documentación solo menciona el 4), incluye la categoría 404 que la documentación no lista y no filtra por HCAESTADO (está comentado). Por confirmar con el dueño del tablero.
- **Priorizados sin filtro de convenio**: El segundo grupo de GESTION_CLINICA toma cualquier convenio con una solicitud de categoría 378; el primero solo 125, 126 y 127.
- **Nombre de tabla**: La documentación original llama NAOS_GESTION_CLINICA y NAOS_CIRUGIAS_PENDIENTES a las tablas que en el modelo se llaman GESTION_CLINICA y CIRUGÍAS PENDIENTES.
- **Vista TABLERO_NAOS**: La lógica de la vista, incluidas CLASIFICACION, SOLICITUD_CAMA y los valores posibles de las marcas, no está documentada. Por confirmar.
- **Pendientes para el dueño del tablero**: Significado de la sigla NAOS, de los estados 4, 5, 6 y 12 de la solicitud, del estado 3 del historial y de TipoCirugiaOid = 1.

## Historial de cambios
- **2026-10-28 · v1**: Esqueleto generado desde data/model_metadata/tablero_naos y hechos del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
