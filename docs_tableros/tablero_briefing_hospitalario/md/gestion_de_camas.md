---
tablero: BRIEFING HOSPITALARIO
pagina: GESTIÓN DE CAMAS
nombre_funcional: Flujo de alistamiento de camas del día (orientador, aseo y acostada del paciente)
bloque: Día
tablas: [GESTIÓN CAMAS]
actualizado: 2026-10-28
version: 2
---

# GESTIÓN DE CAMAS

## Propósito
Muestra, para el día de hoy, en qué paso del alistamiento está cada cama: en espera del orientador, en espera de SAMYL, aseada o ya ocupada, con el tiempo de cada paso y el último usuario que marcó la cama. Sirve para detectar demoras entre la salida de un paciente y el ingreso del siguiente.

## Fuentes de datos
- **GESTIÓN CAMAS**: Registros de marcación de camas con fecha, servicio, cama, estado del flujo (Estado), estado de la cama (HCAESTADO), tiempos de cada paso, colaborador (NOMBRE_COMP) y cargo (carnombre). La consulta de origen no está documentada.

## Indicadores
- **Tiempo espera orientador**: Minutos que la cama lleva esperando al orientador desde su última marca. Columna TIEMPO_ESPERA_ORIENTADOR.
- **Tiempo espera SAMYL**: Minutos que la cama lleva esperando a SAMYL desde su última marca. Columna TIEMPO_ESPERA_SAMYL.
- **Tiempo desde aseo cama**: Minutos transcurridos desde que la cama quedó aseada. Columna CAMA_ASEADA.
- **Tiempo para acostar paciente**: Minutos entre la asignación de la cama al paciente (FecAsigCama de la solicitud de cama) y la marca de paciente acostado. SUM(GESTIÓN CAMAS[PACIENTE_ACOSTADO]).

## Visuales
- **Segmentadores**: CARGO y COLABORADOR.
- **Tabla EN ESPERA ORIENTADOR**: SERVICIO, CAMA, TIEMPO ESPERA ORIENTADOR y ULTIMO USUARIO EN MARCAR. Filtro Estado = 1.
- **Tabla EN ESPERA SAMYL**: SERVICIO, CAMA, TIEMPO ESPERA SAMYL y ULTIMO USUARIO EN MARCAR. Filtro Estado = 2.
- **Tabla CAMAS ASEADAS**: SERVICIO, CAMA, TIEMPO DESDE ASEO CAMA y ULTIMO USUARIO EN MARCAR. Filtros Estado = 3 y cama no ocupada (HCAESTADO distinto de 2).
- **Tabla CAMAS OCUPADAS**: SERVICIO, CAMA, TIEMPO PARA ACOSTAR PACIENTE y ULTIMO USUARIO EN MARCAR. Filtro Estado = 4.

## Reglas de negocio
- **Solo hoy**: Filtro de página de fecha relativa sobre GESTIÓN CAMAS[FECHA] que deja solo los registros del día actual.
- **Pasos del flujo**: Estado 1 en espera de orientador, 2 en espera de SAMYL, 3 cama aseada y 4 cama ocupada.

## Observaciones
- **Sin documentación del propietario**: Esta página no tiene documento .docx; se describe a partir del PBIP y de la consulta del modelo.
- **SAMYL**: El significado de SAMYL (posiblemente el equipo o proveedor de aseo) está por confirmar.
- **Unidades de tiempo**: Todos los tiempos de la consulta están en minutos (DATEDIFF MINUTE); la página no muestra la unidad en los rótulos.
- **Página homónima**: No confundir con GESTIÓN CAMAS, que muestra capacidad y ocupación.
- **Acceso**: Se llega desde el botón GESTIÓN DE CAMAS de la página SOLICITUD CAMAS.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
