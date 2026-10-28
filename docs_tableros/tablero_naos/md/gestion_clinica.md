---
tablero: TABLERO NAOS
pagina: GESTION CLINICA
nombre_funcional: Trámites de gestión clínica pendientes
bloque: Día
tablas: [GESTION_CLINICA, PACIENTES]
actualizado: 2026-10-28
version: 2
---

# GESTION CLINICA

## Propósito
Muestra los trámites de gestión clínica y administrativa abiertos de los pacientes hospitalizados del tablero NAOS, con la categoría de la solicitud y su detalle, para hacer seguimiento a cada gestión. Es seguimiento del estado actual. Se llega con el botón TRÁMITES GESTIÓN CLÍNICA de LISTADO.

## Fuentes de datos
- **GESTION_CLINICA**: Solicitudes de DNSOLISERVICIO_NEW con su categoría (DNCATSERVICIO_NEW), el último seguimiento en estado 3 (DNHISTORIALSS_NEW), el usuario que lo hizo, el ingreso, el paciente y la EPS. Une dos grupos: pacientes en cama de los convenios incluidos y pacientes priorizados.

## Indicadores
- **Tiempo de trámite**: Horas desde el último seguimiento (o desde la creación si no hay seguimiento) hasta la fecha de cierre (o hasta ahora si sigue abierta). Columna TIEMPO_TRAMITE. Unidad: horas.
- **Tiempo para primer seguimiento**: Horas desde la creación de la solicitud hasta el seguimiento tomado (o hasta ahora si no hay). Columna TIEMPO_PARA_PRIMER_SEGUIMIENTO. Unidad: horas.

## Visuales
- **Botón de inicio**: Icono de casa que regresa a LISTADO.
- **Filtros de segmentación**: Listas de INGRESO, SERVICIO y TIPO PACIENTE.
- **Tabla trámites gestión clínica**: Columnas PACIENTE, DOCUMENTO PACIENTE, CATEGORIA SOLICITUD, INGRESO y el texto de la solicitud; una fila por solicitud.

## Reglas de negocio
- **Categorías incluidas**: Solo solicitudes de las categorías 171, 172, 174, 177, 178, 179, 180, 181, 182, 183, 229, 289, 367, 375, 377, 384 y 404 (según la consulta del modelo; la documentación original no lista la 404).
- **Solicitudes abiertas**: Se excluyen las solicitudes en estados 4, 5, 6 y 12 (según la consulta del modelo; la documentación original solo menciona el 4).
- **Pacientes hospitalizados**: Solo ingresos sin egreso (ADNEGRESO vacío).
- **Primer grupo**: Pacientes con convenio 125 (prepagada), 126 (póliza) o 127 (particular). El filtro de cama en estado 2 (HCAESTADO = 2) está comentado en la consulta del modelo y no se aplica.
- **Segundo grupo priorizado**: Ingresos que tienen además una solicitud de la categoría 378 (paciente priorizado), sin importar cama ni convenio.
- **Fecha nula del sistema**: La fecha 1969-12-31 19:00 se trata como vacía en ambos tiempos.

## Observaciones
- **Nombre de página**: La página se llama GESTION CLINICA en Power BI; la documentación original la llama «NAOS-GESTION CLINICA» y el botón «TRÁMITES GESTIÓN CLÍNICA».
- **Primer seguimiento mal nombrado**: TIEMPO_PARA_PRIMER_SEGUIMIENTO usa el último seguimiento (TOP 1 ordenado por Oid descendente), no el primero.
- **Significado de estados**: Por confirmar qué representan los estados 4, 5, 6 y 12 de la solicitud y el estado 3 del historial.
- **Filtros por relación**: GESTION_CLINICA no tiene columnas de servicio ni tipo de paciente; los filtros de esos campos llegan desde PACIENTES por la relación PACIENTES[AINCONSEC] → GESTION_CLINICA[AINCONSEC] (muchos a muchos, en ambos sentidos).
- **Segundo grupo sin filtro de convenio**: Los ingresos priorizados entran con cualquier convenio, aunque la documentación original los describe sin aclararlo.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
