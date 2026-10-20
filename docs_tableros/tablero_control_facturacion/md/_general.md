---
tablero: TABLERO CONTROL FACTURACION
pagina: GENERAL
nombre_funcional: Control del proceso de facturación de cuentas de pacientes
bloque: General
tablas: [ULT_GESTION, FACTURACION PERFILES, ENPROCESO_FACTURACION, PENDIENTES_FACTURACION, FACTURADORES, FACTURACION, CALENDARIO, DIM_TIPO_INGRESO]
actualizado: 2026-10-20
version: 1
---

# GENERAL

## Propósito
Controla el proceso de facturación de las cuentas de los pacientes desde el egreso hasta la radicación: ingresos abiertos y su valor estimado, egresos pendientes de iniciar trámite, tiempos de gestión en cada etapa (perfil), cuentas en proceso con semáforo de días, trazabilidad por responsable y producción por facturador. INICIO es la página principal; desde ella y desde RESUMEN FACTURACION se navega a las demás.

## Fuentes de datos
- **Origen de los datos**: Consultas SQL a Dinámica Gerencial (DGEMPRES10: ingresos, egresos, facturas, servicios) y a PLANILLAUSUARIO (trazabilidad de cuentas TFACTURACI y TFESTADOH, solicitudes de auditoría), además de dimensiones de la bodega de datos (DIM_INGRESO, DIM_EGRESO, DIM_USUARIOS, DIM_ESTADO_HISTORIA, SLNFACTUR_DW).
- **ULT_GESTION**: Ingresos abiertos con su última gestión; alimenta TRAZABILIDAD. INICIO usa la misma consulta; por confirmar si es la misma tabla.
- **FACTURACION PERFILES**: Una fila por cuenta y perfil con fechas de recibe y entrega; alimenta RESUMEN FACTURACION, las páginas por perfil y PROCESO FACTURACION.
- **ENPROCESO_FACTURACION**: Última etapa de cada cuenta con sus días en proceso; alimenta las páginas EN PROCESO.
- **PENDIENTES_FACTURACION**: Egresos sin trazabilidad de facturación; alimenta FACTURACION PENDIENTE.
- **FACTURADORES**: Facturas no anuladas con su facturador y monto; alimenta FACTURADORES.
- **FACTURACION**: Fechas de recibe y entrega de cada etapa en columnas, por ingreso; alimenta TIEMPOS.
- **Periodo cargado**: La mayoría de consultas traen egresos o facturas desde el 1 de agosto de 2025; las de INICIO y TRAZABILIDAD no tienen límite de fecha.

## Definiciones
- **Ingreso**: Admisión del paciente en Dinámica (ADNINGRESO); su consecutivo (AINCONSEC) es el número de ingreso que muestran las tablas.
- **Egreso**: Salida del paciente (ADNEGRESO, fecha ADEFECSAL); desde el egreso empieza el trámite de la cuenta.
- **Trazabilidad de la cuenta**: Registro en PLANILLAUSUARIO (TFACTURACI y su historial TFESTADOH) de cada paso de la cuenta por las áreas del proceso, con quién y cuándo la recibe y la entrega.
- **Perfil**: Etapa o área del proceso que recibe y entrega la cuenta (TFTIPPERFIL): 1 ESTACION DE ENFERMERIA, 2 y 13 FACTURACION, 3 CUENTAS, 4 AUDITORIA PERTINENCIA, 5 AUDITORIA MEDICAMENTOS, 7 a 9 MODIFICACIONES (medicamentos, laboratorios, facturas), 10 ESCANEO FOTOCOPIAS, 11 GESTION DE LA INFORMACION Y ARCHIVO, 12 CUENTAS NO POS, 15 AUDITORES EXTERNOS, 16 GLOSAS, 17 RADICACION DE CUENTAS, 20 FACTURA ENTIDAD, 21 FACTURACION IMAGENES, 22 REGISTRO DE CUENTAS, 23 TRAMITE DE AUTORIZACIONES y 24 CONSULTA AMBULATORIA.
- **Recibe y entrega**: Fecha en que un perfil recibe la cuenta (FECHA_RECIBE) y fecha en que la entrega al siguiente (FECHA_ENTREGA). En auditorías (perfiles 4 y 5) recibe es la asignación (estado 2) y entrega es la respuesta (estado 4) de la solicitud de auditoría (servicio categoría 374).
- **Tiempo de gestión**: Horas entre recibe y entrega de un perfil. Columna 'FACTURACION PERFILES'[TIEMPO] = DATEDIFF(FECHA_RECIBE, FECHA_ENTREGA, HOUR).
- **Estado de la factura**: FACTURADA si el ingreso tiene factura no anulada (SFADOCANU = 0), ANULADA si está anulada (SFADOCANU = 1) y OTRO si aún no tiene factura. Solo aplica a ingresos con AINESTADO 0 o 1.
- **Tipo de ingreso**: AINTIPING 1 es AMBULATORIO y 2 es HOSPITALARIO.
- **Valor estimado**: Suma del valor de los servicios cargados al ingreso (SLNSERPRO.SERVALENT); es lo que se espera facturar.
- **Radicación**: Entrega formal de la factura a la entidad responsable del pago; es la etapa final (perfil 17).
- **Glosa**: Objeción de la entidad pagadora a una factura; tiene su propio perfil (16).

## Reglas de negocio
- **Primera gestión por perfil**: Las tablas de tiempos toman, para cada cuenta y perfil, el primer registro de recibe (el más antiguo).
- **Ingresos válidos**: Las tablas de tiempos y en proceso solo incluyen ingresos con AINESTADO 0 o 1 y egreso desde el 1 de agosto de 2025 hasta hoy.
- **Filtro AMBULATORIO/HOSPITALARIO**: Varias páginas tienen un segmentador de botones por tipo de ingreso.

## Observaciones
- **PBIP incompleto**: El PBIP local solo trae 7 páginas (EN PROCESO AUDITORIA MEDICAMENTOS, CUENTAS, ESCANEO FOTOCOPIAS, FACTURADORES, TIEMPOS, ESTACION ENFERMERIA y una sin nombre); los demás nombres de página se toman de la documentación y están por confirmar.
- **Dos perfiles FACTURACION**: Los códigos 2 y 13 se llaman igual (FACTURACION); un filtro por PERFIL = FACTURACION incluye ambos. En TIEMPOS el 2 se llama «FACTURADOR SERVICIO».
- **Nombre de tabla**: La documentación escribe FACTURACION_PERFILES pero el DAX y el PBIP usan 'FACTURACION PERFILES'. Por confirmar si son la misma tabla.
- **Auditor por usuario**: En las consultas de tiempos, la auditoría se liga al perfil 4 o 5 por el usuario que entrega y no por el ingreso; un usuario que trabaje en ambos perfiles podría duplicar filas. Por confirmar.
- **Códigos AINESTADO**: El significado de cada estado del ingreso (0 a 4) está por confirmar; cada consulta usa un conjunto distinto.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
