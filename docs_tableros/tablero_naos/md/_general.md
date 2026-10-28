---
tablero: TABLERO NAOS
pagina: GENERAL
nombre_funcional: Seguimiento de pacientes hospitalizados con pendientes activos
bloque: General
tablas: [PACIENTES, EXAMENES, ResumenExamenes, GESTION_CLINICA, CIRUGÍAS PENDIENTES]
actualizado: 2026-10-28
version: 2
---

# GENERAL

## Propósito
Tablero operativo para el seguimiento diario de pacientes hospitalizados de medicina prepagada, póliza, particular y plan complementario que tienen pendientes activos: estancia prolongada, solicitud de cama, dieta, exámenes, trámites de gestión clínica o cirugías. Muestra el estado actual, no un histórico. La página LISTADO es la principal y lleva a EXAMENES PENDIENTES, GESTION CLINICA y CIRUGIAS PENDIENTES.

## Fuentes de datos
- **Vista TABLERO_NAOS**: Se carga completa (SELECT * FROM TABLERO_NAOS) en la tabla PACIENTES; trae un registro por paciente con servicio, cama, aseguradora, clasificación, días de estancia y marcas de pendientes. Su lógica interna no está documentada.
- **Solicitudes de gestión clínica**: Solicitudes de servicio de DNSOLISERVICIO_NEW con su categoría, último seguimiento, usuario asignado, paciente, ingreso y EPS (tabla GESTION_CLINICA).
- **Solicitudes de cirugía**: Solicitudes de programación quirúrgica de Qx_SolicitudProgramacion con paciente, especialidad, procedimientos, médico, estado actual y tipo de paciente (tabla CIRUGÍAS PENDIENTES).

## Definiciones
- **Paciente con pendiente activo**: Paciente hospitalizado, sin egreso, que tiene al menos un pendiente de estancia, cama, dieta, examen, gestión clínica o cirugía.
- **Tipo de paciente**: Clasificación por convenio (GDECONFAC): 125 MEDICINA PREPAGADA, 126 PÓLIZA, 127 PARTICULAR y 122 PLAN COMPLEMENTARIO.
- **Paciente priorizado**: Paciente cuyo ingreso tiene una solicitud de gestión clínica de la categoría 378; aparece como PACIENTE PRIORIZADO en la clasificación.
- **Días de estancia**: Días que lleva hospitalizado el paciente (PACIENTES[DIAS_ESTANCIA]).
- **Trámite de gestión clínica**: Solicitud clínica o administrativa abierta para un ingreso (por ejemplo, hallazgos quirúrgicos, trámite de patologías, solicitud de cirugía).

## Reglas de negocio
- **Solo pacientes sin egreso**: Las solicitudes de gestión clínica se limitan a ingresos sin fecha de egreso (ADNEGRESO vacío).
- **Convenios incluidos**: Gestión clínica toma convenios 125, 126 y 127; cirugías pendientes toma 125, 126, 127 y 122.
- **Fecha nula del sistema**: La fecha 1969-12-31 19:00 se trata como vacía en los cálculos de tiempos.

## Observaciones
- **Significado de NAOS**: La documentación no explica la sigla NAOS. Por confirmar.
- **Vista sin documentar**: La consulta de PACIENTES es SELECT * FROM TABLERO_NAOS; los criterios para que un paciente aparezca están en la vista y no en la documentación. Por confirmar.
- **Relaciones entre tablas**: PACIENTES se relaciona con GESTION_CLINICA y ResumenExamenes por AINCONSEC; el detalle está en el diccionario.
- **Sin medidas**: El modelo no define medidas DAX; las tarjetas cuentan columnas. Las medidas del catálogo local son inferidas de la documentación.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
