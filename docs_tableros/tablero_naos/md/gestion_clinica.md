---
tablero: TABLERO NAOS
pagina: GESTION CLINICA
nombre_funcional: Trámites de gestión clínica pendientes
bloque: Día
tablas: [NAOS_GESTION_CLINICA]
actualizado: 2026-10-20
version: 1
---

# GESTION CLINICA

## Propósito
Muestra los trámites de gestión clínica y administrativa abiertos de los pacientes hospitalizados del tablero NAOS, con la categoría de la solicitud y su detalle, para hacer seguimiento a cada gestión. Es seguimiento del estado actual. Se llega con el botón TRÁMITES GESTIÓN CLÍNICA de LISTADO.

## Fuentes de datos
- **NAOS_GESTION_CLINICA**: Solicitudes de DNSOLISERVICIO_NEW con su categoría (DNCATSERVICIO_NEW), el último seguimiento en estado 3 (DNHISTORIALSS_NEW), el usuario que lo hizo, el ingreso, el paciente y la EPS. Une dos grupos: pacientes en cama de los convenios incluidos y pacientes priorizados.

## Indicadores
- **Tiempo de trámite**: Horas desde el último seguimiento (o desde la creación si no hay seguimiento) hasta la fecha de cierre (o hasta ahora si sigue abierta). Columna TIEMPO_TRAMITE. Unidad: horas.
- **Tiempo para primer seguimiento**: Horas desde la creación de la solicitud hasta el seguimiento tomado (o hasta ahora si no hay). Columna TIEMPO_PARA_PRIMER_SEGUIMIENTO. Unidad: horas.

## Visuales
- **Botón de inicio**: Icono de casa que regresa a LISTADO.
- **Filtros de segmentación**: Listas de INGRESO, SERVICIO y TIPO PACIENTE.
- **Tabla trámites gestión clínica**: Columnas PACIENTE, DOCUMENTO PACIENTE, CATEGORIA SOLICITUD, INGRESO y el texto de la solicitud; una fila por solicitud.

## Reglas de negocio
- **Categorías incluidas**: Solo solicitudes de las categorías 171, 172, 174, 177, 178, 179, 180, 181, 182, 183, 229, 289, 367, 375, 377 y 384.
- **Solicitudes abiertas**: Se excluyen las solicitudes en estado 4.
- **Pacientes hospitalizados**: Solo ingresos sin egreso (ADNEGRESO vacío).
- **Primer grupo**: Pacientes con cama en estado 2 (HCAESTADO = 2) y convenio 125 (prepagada), 126 (póliza) o 127 (particular).
- **Segundo grupo priorizado**: Ingresos que tienen además una solicitud de la categoría 378 (paciente priorizado), sin importar cama ni convenio.
- **Fecha nula del sistema**: La fecha 1969-12-31 19:00 se trata como vacía en ambos tiempos.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar; la documentación la llama «NAOS-GESTION CLINICA» y el botón «TRÁMITES GESTIÓN CLÍNICA».
- **Primer seguimiento mal nombrado**: TIEMPO_PARA_PRIMER_SEGUIMIENTO usa el último seguimiento (TOP 1 ordenado por Oid descendente), no el primero.
- **Significado de estados**: Por confirmar qué representan el estado 4 de la solicitud, el estado 3 del historial y el estado 2 de la cama.
- **Filtros por relación**: La tabla no tiene columnas de servicio ni tipo de paciente; por confirmar cómo se aplican esos filtros.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
