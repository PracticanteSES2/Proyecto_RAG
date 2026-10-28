---
tablero: TABLERO REFERENCIA
pagina: DICCIONARIO
nombre_funcional: Diccionario de variables del tablero
bloque: Diccionario
tablas: [CONTRARREFERENCIA, DETALLE_RECEPCIONES, DETALLE_REMISIONES, REFERENCIA]
actualizado: 2026-10-28
version: 2
---

# DICCIONARIO

## Propósito
Diccionario de variables del tablero TABLERO REFERENCIA: qué es cada tabla, medida y columna clave del modelo «TABLERO REFERENCIA», con su cálculo y dónde se usa. Se genera del modelo y de los visuales; las descripciones de negocio marcadas «Por confirmar» las completa quien conoce el tablero.

## Tablas
- **CONTRARREFERENCIA**: Remisiones de pacientes del hospital a otras instituciones (seguimiento de remisiones) con ingreso en los últimos 90 días, con servicio de origen, EPS, motivo, especialidad y fecha de aceptación. Origen: consulta SQL sobre SEGUIMIENTO_REMISIONES_DW en la base DWSES (Import). Granularidad: una fila por remisión (OidRemision). Columnas principales: Cedula, Column1, ConsecIngreso, EPS_PACIENTE, Expr3, FECHACEPTACION, FechaIngreso, FechaRemision y 9 más.
- **DETALLE_RECEPCIONES**: Bitácora de seguimiento de las solicitudes de recepción: anotaciones (llamadas, validaciones, trámites) con su fecha, si requieren alerta y si fueron verificadas, desde el 1 de enero de 2023. Origen: consulta SQL sobre OBSERVACIONES_RECEPCION_DW, DIM_USUARIOS en la base DWSES (Import). Granularidad: una fila por anotación; una solicitud (REFERENCIA[OID]) puede tener varias. Columnas principales: Descripcion, EsAlerta, EsVerificado, FechaRegistro, FechaVerificado, NOMBRE_REGISTRA, Oid, RecepcionSegOid y 6 más.
- **DETALLE_REMISIONES**: Histórico de remisiones (HISTORICO_REMISIONES_DW) registradas desde el 1 de enero de 2023. Alimenta DETALLE REMISION y SEGUIMIENTOS REMISION. Origen: consulta SQL sobre HISTORICO_REMISIONES_DW en la base DWSES (Import). Granularidad: una fila por anotación de seguimiento de una remisión (OidRemision); una remisión puede tener varias. Columnas principales: Descripcion, EsAlerta, EsVerificado, FechaRegistro, FechaVerificado, NOMBRE_COMPLETO, Oid, OidRemision y 6 más.
- **REFERENCIA**: Solicitudes de recepción (RECEPCIONES_DW) con llamada en los últimos 30 días, con su causa de no aceptación (SEG_RECEPCIONES) y la fecha de no aceptación (HISTORICO_RECEPCIONES_DW). Origen: consulta SQL sobre RECEPCIONES_DW, SEG_RECEPCIONES, HISTORICO_RECEPCIONES_DW en la base DWSES (Import). Granularidad: una fila por solicitud de recepción (OID) con llamada en los últimos 30 días. Columnas principales: ESTADO, ANOS, CAUSA, CAUSA_MAYUSC, FECHAACEPTADO, FECHAESTIMACIONLLEGADA, FECHAINGRESO, FECHALLAMADA y 14 más.

## Columnas calculadas
- **CONTRARREFERENCIA[RANGO_TIEMPO]**: Agrupa el tiempo de respuesta de la remisión en rangos: 0-24 HORAS, 24-72 HORAS, 72-120 HORAS y MAYOR A 120 HORAS (en horas, según TIEMPO_RESPUESTA); queda en blanco si el tiempo es negativo o no hay fecha de remisión. Tipo: texto. Cálculo: `IF(CONTRARREFERENCIA[TIEMPO_RESPUESTA]>=0 && CONTRARREFERENCIA[TIEMPO_RESPUESTA]<=24,"0-24 HORAS",IF(CONTRARREFERENCIA[TIEMPO_RESPUESTA]>24 && CONTRARREFERENCIA[TIEMPO_RESPUESTA]<=72,"24-72 HORAS",IF(CONTRARREFERENCIA[TIEMPO_RESPUESTA]>72 && CONTRARREFERENCIA[TIEMPO_RESPUESTA]<=120,"72-120 HORAS",IF(CONTRARREFERENCIA[TIEMPO_RESPUESTA]>120,"MAYOR A 120 HORAS"))))`. Se usa en: no aparece en visuales ni filtros del informe.
- **CONTRARREFERENCIA[TIEMPO_RESPUESTA]**: Horas entre la fecha de remisión (FechaRemision) y la fecha de aceptación (FECHACEPTACION); si no hay aceptación posterior a la remisión, se cuenta hasta hoy. Tipo: entero. Cálculo: `DATEDIFF(CONTRARREFERENCIA[FechaRemision],IF(CONTRARREFERENCIA[FECHACEPTACION]>CONTRARREFERENCIA[FechaRemision],CONTRARREFERENCIA[FECHACEPTACION],TODAY()),HOUR)`. Se usa en: no aparece en visuales ni filtros del informe.
- **DETALLE_RECEPCIONES[NOMBRE_REGISTRA]**: Nombre completo en mayúsculas del usuario que registró la anotación (nombres y apellidos de DIM_USUARIOS). Tipo: texto. Cálculo: `UPPER(CONCATENATE(DETALLE_RECEPCIONES[usu_nombres],CONCATENATE(" ",DETALLE_RECEPCIONES[usu_apellidos])))`. Se usa en: no aparece en visuales ni filtros del informe.
- **DETALLE_REMISIONES[NOMBRE_COMPLETO]**: Nombre completo del usuario que registró la anotación de remisión (USU_NOMBRES y USU_APELLIDOS separados por un espacio). Tipo: texto. Cálculo: `CONCATENATE(DETALLE_REMISIONES[USU_NOMBRES],CONCATENATE(" ",DETALLE_REMISIONES[USU_APELLIDOS]))`. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[CAUSA_MAYUSC]**: Causa de no aceptación en mayúsculas, para que no se separen causas escritas con distinta capitalización; en blanco si la solicitud no tiene causa. Tipo: texto. Cálculo: `UPPER(REFERENCIA[CAUSA])`. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[RANGO_EDAD]**: 0-17 AÑOS, 18 A 65 AÑOS y MAYORES DE 65 AÑOS según la edad en años (ANOS). Columna REFERENCIA[RANGO_EDAD]. Tipo: texto. Cálculo: `IF(REFERENCIA[ANOS]>=0 && REFERENCIA[ANOS]<18,"0-17 AÑOS",IF(REFERENCIA[ANOS]>=18 && REFERENCIA[ANOS]<=65,"18 A 65 AÑOS",IF(REFERENCIA[ANOS]>65,"MAYORES DE 65 AÑOS")))`. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[RANGO_REMISION]**: Agrupación del tiempo de respuesta: 0-24 HORAS, 24-72 HORAS, 72-120 HORAS y MAYOR A 120 HORAS. Columna REFERENCIA[RANGO_REMISION]. Tipo: texto. Cálculo: `IF(DATEDIFF(REFERENCIA[FECHALLAMADA],IF(NOT(ISBLANK(REFERENCIA[FechaNoAceptado])),REFERENCIA[FechaNoAceptado],IF(NOT(ISBLANK(REFERENCIA[FechaAceptado])),REFERENCIA[FechaAceptado],TODAY())),HOUR)>=0 &&DATEDIFF(REFERENCIA[FECHALLAMADA],IF(NOT(ISBLANK(REFERENCIA[FechaNoAceptado])),REFERENCIA[FechaNoAceptado],IF(NOT(ISBLANK(REFERENCIA[FechaAceptado])),REFERENCIA[FechaAceptado],TODAY())),HOUR)<=24,"0-24 HORAS",IF(DATEDIFF(REFERENCIA[FECHALLAMADA],IF(NOT(ISBLANK(REFERENCIA[FechaNoAceptado])),REFERENCIA[FechaNoAceptado],IF(NOT(ISBLANK(REFERENCIA[FechaAceptado])),REFERENCIA[FechaAceptado],TODAY())),HOUR)>24 &&DATEDIFF(REFERENCIA[FECHALLAMADA],IF(NOT(ISBLANK(REFERENCIA[FechaNoAceptado])),REFERENCIA[FechaNoAceptado],IF(NOT(ISBLANK(REFERENCIA[FechaAceptado])),REFERENCIA[FechaAceptado],TODAY())),HOUR)<=72,"24-72 HORAS",IF(DATEDIFF(REFERENCIA[FECHALLAMADA],IF(NOT(ISBLANK(REFERENCIA[FechaNoAceptado])),REFERENCIA[FechaNoAceptado],IF(NOT(ISBLANK(REFERENCIA[FechaAceptado])),REFERENCIA[FechaAceptado],TODAY())),HOUR)>72 && DATEDIFF(REFERENCIA[FECHALLAMADA],IF(NOT(ISBLANK(REFERENCIA[FechaNoAceptado])),REFERENCIA[FechaNoAceptado],IF(NOT(ISBLANK(REFERENCIA[FechaAceptado])),REFERENCIA[FechaAceptado],TODAY())),HOUR)<=120,"72-120 HORAS",IF(DATEDIFF(REFERENCIA[FECHALLAMADA],IF(NOT(ISBLANK(REFERENCIA[FechaNoAceptado])),REFERENCIA[FechaNoAceptado],IF(NOT(ISBLANK(REFERENCIA[FechaAceptado])),REFERENCIA[FechaAceptado],TODAY())),HOUR)>120,"MAYOR A 120 HORAS"))))`. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[TIEMPO_REMISION]**: Horas entre la llamada y la fecha de no aceptación; si no la hay, la de aceptación; si no hay ninguna, hasta hoy. Columna REFERENCIA[TIEMPO_REMISION]. Tipo: entero. Cálculo: `DATEDIFF(REFERENCIA[FECHALLAMADA],IF(NOT(ISBLANK(REFERENCIA[FechaNoAceptado])),REFERENCIA[FechaNoAceptado],IF(NOT(ISBLANK(REFERENCIA[FechaAceptado])),REFERENCIA[FechaAceptado],TODAY())),HOUR)`. Se usa en: no aparece en visuales ni filtros del informe.

## Columnas clave
- **REFERENCIA[ESTADO]**: Estado de la solicitud de recepción (nombre del estado en RECEPCIONES_DW). Tipo: texto. Valores: No Aceptado (estado 3, rechazada), Aceptado, Con Ingreso, Tramite Por SES, Es Urgencia Vital. Se usa en: DETALLE NO ACEPTADOS RECEPCION › Filtro de la página; DETALLE ACEPTADOS RECEPCION › Filtro de la página; DETALLE_RECEPCIONES › Filtro de la página; DETALLE REMISION › Filtro de la página; SEGUIMIENTOS REMISION › Filtro de la página.
- **REFERENCIA[OID]**: Identificador de la solicitud de recepción. Tipo: entero. Valores: único por solicitud. Se usa en: la relación con DETALLE_RECEPCIONES[RecepcionSegOid].
- **REFERENCIA[FECHALLAMADA]**: Fecha y hora de la llamada con que otra institución pide remitir al paciente; inicio del tiempo de respuesta. Tipo: fecha. Se usa en: REFERENCIA[TIEMPO_REMISION], REFERENCIA[RANGO_REMISION] y el filtro de 30 días de la consulta.
- **REFERENCIA[FECHAACEPTADO]**: Fecha en que el hospital aceptó la solicitud; vacía si no se aceptó. Tipo: fecha. Se usa en: REFERENCIA[TIEMPO_REMISION].
- **REFERENCIA[FechaNoAceptado]**: Fecha del último cambio al estado 3 (No Aceptado) en el histórico de la solicitud; vacía si no está en ese estado. Tipo: fecha. Se usa en: REFERENCIA[TIEMPO_REMISION].
- **REFERENCIA[FECHAINGRESO]**: Fecha de ingreso del paciente al hospital; valores como 31/12/1969 o 01/01/1900 indican que aún no ingresó. Tipo: fecha. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[FECHAESTIMACIONLLEGADA]**: Fecha estimada de llegada del paciente informada en la solicitud. Tipo: fecha. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[CAUSA]**: Causa de no aceptación registrada en SEG_RECEPCIONES; en blanco si la solicitud no tiene causa. Tipo: texto. Valores: por ejemplo supera la capacidad instalada, no disponibilidad de cama, aceptado por otra institución. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[ANOS]**: Edad del paciente en años. Tipo: entero. Unidad: años. Se usa en: REFERENCIA[RANGO_EDAD].
- **REFERENCIA[GEEDESCRI]**: Especialidad solicitada. Tipo: texto. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[nombreps]**: Nombre de la EPS del paciente. Tipo: texto. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[PRESTADOR]**: Institución que solicita la recepción. Tipo: texto. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[SERVICIO]**: Servicio del hospital solicitado. Tipo: texto. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[Motivo]**: Motivo de la solicitud. Tipo: texto. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[USUREGISTRA]**: Usuario que registra la solicitud. Tipo: texto. Se usa en: no aparece en visuales ni filtros del informe.
- **REFERENCIA[USUACEPTA]**: Usuario que acepta la solicitud. Tipo: texto. Se usa en: no aparece en visuales ni filtros del informe.
- **CONTRARREFERENCIA[OidRemision]**: Identificador de la remisión. Tipo: entero. Se usa en: la relación con DETALLE_REMISIONES[OidRemision].
- **CONTRARREFERENCIA[FechaRemision]**: Fecha de la solicitud de remisión; inicio de TIEMPO_RESPUESTA. Tipo: fecha. Se usa en: no aparece en visuales ni filtros del informe.
- **CONTRARREFERENCIA[FECHACEPTACION]**: Fecha en que la institución receptora aceptó la remisión; fin de TIEMPO_RESPUESTA. Tipo: fecha. Se usa en: no aparece en visuales ni filtros del informe.
- **CONTRARREFERENCIA[EPS_PACIENTE]**: EPS del paciente remitido. Tipo: texto. Valores: incluye el año del contrato (por ejemplo «NUEVA EPS CONT 2026»). Se usa en: no aparece en visuales ni filtros del informe.
- **CONTRARREFERENCIA[ServicioSes]**: Servicio del hospital desde el que se remite al paciente. Tipo: texto. Se usa en: no aparece en visuales ni filtros del informe.
- **CONTRARREFERENCIA[Column1]**: Motivo de la remisión (CAST(Motivo AS TEXT) en la consulta). Tipo: texto. Se usa en: no aparece en visuales ni filtros del informe.
- **CONTRARREFERENCIA[Nombre]**: Nombre del estado de la remisión (probable); por confirmar. Tipo: texto. Valores: Registrado, Aceptado Remision, Cancelado según la documentación. Se usa en: no aparece en visuales ni filtros del informe.
- **CONTRARREFERENCIA[Expr3]**: Por confirmar. Tipo: texto. Se usa en: no aparece en visuales ni filtros del informe.
- **CONTRARREFERENCIA[FechaIngreso]**: Fecha de ingreso del paciente al hospital; la consulta solo trae remisiones con ingreso en los últimos 90 días. Tipo: fecha. Se usa en: no aparece en visuales ni filtros del informe.
- **CONTRARREFERENCIA[FechaSalida]**: Fecha de salida del paciente del hospital. Tipo: fecha. Se usa en: no aparece en visuales ni filtros del informe.
- **DETALLE_RECEPCIONES[Descripcion]**: Texto libre de la anotación de seguimiento; puede contener información clínica sensible. Tipo: texto. Se usa en: no aparece en visuales ni filtros del informe.
- **DETALLE_RECEPCIONES[EsAlerta]**: Indica si la anotación está marcada como alerta. Tipo: verdadero/falso. Se usa en: no aparece en visuales ni filtros del informe.
- **DETALLE_RECEPCIONES[EsVerificado]**: Indica si la anotación fue verificada. Tipo: verdadero/falso. Se usa en: no aparece en visuales ni filtros del informe.
- **DETALLE_REMISIONES[Descripcion]**: Texto libre de la anotación de seguimiento de la remisión; puede contener información clínica sensible. Tipo: texto. Se usa en: no aparece en visuales ni filtros del informe.
- **DETALLE_REMISIONES[EsAlerta]**: Indica si la anotación está marcada como alerta. Tipo: verdadero/falso. Se usa en: no aparece en visuales ni filtros del informe.
- **DETALLE_REMISIONES[EsVerificado]**: Indica si la anotación fue verificada. Tipo: verdadero/falso. Se usa en: no aparece en visuales ni filtros del informe.

## Relaciones
- **DETALLE_RECEPCIONES[RecepcionSegOid] → REFERENCIA[OID]**: Cada anotación de seguimiento se asocia a su solicitud por RecepcionSegOid = OID. Muchos a muchos, REFERENCIA filtra a DETALLE_RECEPCIONES, activa.
- **DETALLE_REMISIONES[OidRemision] → CONTRARREFERENCIA[OidRemision]**: Cada anotación de seguimiento se asocia a su remisión por OidRemision. Muchos a uno, CONTRARREFERENCIA filtra a DETALLE_REMISIONES, activa.

## Observaciones
- **Informe sin visuales**: El PBIP local solo trae las páginas (sin visuales), por lo que «Se usa en» de las columnas solo muestra los filtros de página. Por confirmar qué visuales usan cada columna.
- **Documentación de remisión**: La documentación original de seguimiento de remisión describe la consulta de DETALLE_REMISIONES, pero sus columnas (EPS, fecha de remisión, aceptación, rango de tiempo) están en CONTRARREFERENCIA. Por confirmar de qué tabla se alimenta cada visual.
- **Rangos de CONTRARREFERENCIA**: RANGO_TIEMPO deja en blanco los tiempos negativos; una aceptación anterior a la remisión (fecha por defecto) se trata como sin aceptar y cuenta hasta hoy.
- **Fecha de no aceptación**: En la consulta de REFERENCIA, FechaNoAceptado usa FechaEdicion sin alias en el CASE; por confirmar si toma la fecha de HISTORICO_RECEPCIONES_DW (alias D) o la de la solicitud.
- **Columnas por confirmar**: CONTRARREFERENCIA[Expr3] y el significado exacto de CONTRARREFERENCIA[Nombre].

## Historial de cambios
- **2026-10-28 · v1**: Esqueleto generado desde data/model_metadata/tablero_referencia y hechos del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
