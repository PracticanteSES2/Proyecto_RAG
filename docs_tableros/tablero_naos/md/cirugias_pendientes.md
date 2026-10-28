---
tablero: TABLERO NAOS
pagina: CIRUGÍAS PENDIENTES
nombre_funcional: Cirugías pendientes de pacientes NAOS
bloque: Día
tablas: [CIRUGÍAS PENDIENTES]
actualizado: 2026-10-28
version: 2
---

# CIRUGÍAS PENDIENTES

## Propósito
Muestra los pacientes de medicina prepagada, póliza, particular y plan complementario con solicitudes de cirugía pendientes, con sus procedimientos y especialidad, para planear y seguir la programación quirúrgica. Es seguimiento del estado actual. Se llega con el botón CIRUGÍAS PENDIENTES de LISTADO.

## Fuentes de datos
- **CIRUGÍAS PENDIENTES**: Solicitudes de Qx_SolicitudProgramacion con documento y nombre del paciente, EPS, especialidad, procedimientos, médico, fecha de programación, estado actual, fecha de registro y tipo de paciente.

## Indicadores
- **Total de cirugías pendientes**: Cantidad de solicitudes de cirugía pendientes según los filtros. Unidad: solicitudes. Agregación por confirmar.

## Visuales
- **Botón de inicio**: Icono de casa que regresa a LISTADO.
- **Tarjeta cirugías pendientes**: Número total con el rótulo CIRUGÍAS PENDIENTES.
- **Filtros de segmentación**: Listas de TIPO PACIENTE, ESPECIALIDAD y EPS.
- **Tabla cirugías pendientes**: Columnas DOCUMENTO, PACIENTE, PROCEDIMIENTO y ESPECIALIDAD; una fila por solicitud.

## Reglas de negocio
- **Estados incluidos**: Solo solicitudes en estado quirúrgico 1 (planeada), 4, 5 (en trámite clínico o administrativo) o 7 (paciente programado).
- **Tipo de cirugía**: Solo solicitudes con TipoCirugiaOid = 1.
- **Tipo de paciente**: Convenio 125 es MEDICINA PREPAGADA, 126 PÓLIZA, 127 PARTICULAR y 122 PLAN COMPLEMENTARIO; otros convenios no entran.
- **Procedimientos**: Los procedimientos de la solicitud se unen en una sola celda separados por « * ».
- **Médico**: Si el médico tiene el código 5000 se muestra el nombre escrito en la solicitud (MedicoSolicita); si no, el nombre del médico registrado.
- **Fecha de programación**: Paciente Programado es la primera fecha en que la solicitud pasó al estado 7.

## Observaciones
- **Nombre de página**: La página se llama CIRUGÍAS PENDIENTES en Power BI; la documentación original la llama «NAOS-CIRUGIAS PENDIENTES».
- **Estado 4 sin nombre**: La documentación no dice qué estado es el 4. Por confirmar.
- **Visual de la tabla**: La tabla del informe se titula «DOCUMENTO» e incluye también EPS, FechaRegistro y TIPO_PACIENTE además de las columnas listadas.
- **Tipo de cirugía 1**: Por confirmar qué tipo representa TipoCirugiaOid = 1 (por ejemplo, programada).
- **Procedimientos vacíos**: En la captura hay solicitudes sin procedimiento; ocurre cuando la solicitud no tiene procedimientos asociados.
- **Sin filtro de fecha ni de egreso**: La consulta no limita por fecha ni por egreso; por confirmar si incluye pacientes ya egresados o ambulatorios.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
