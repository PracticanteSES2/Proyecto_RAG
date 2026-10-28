---
tablero: BRIEFING HOSPITALARIO
pagina: GESTIÓN DE CAMAS
nombre_funcional: Flujo de alistamiento de camas del día (orientador, aseo y acostada del paciente)
bloque: Día
tablas: [GESTIÓN CAMAS]
actualizado: 2026-10-20
version: 1
---

# GESTIÓN DE CAMAS

## Propósito
Muestra, para el día de hoy, en qué paso del alistamiento está cada cama: en espera del orientador, en espera de SAMYL, aseada o ya ocupada, con el tiempo de cada paso y el último usuario que marcó la cama. Sirve para detectar demoras entre la salida de un paciente y el ingreso del siguiente.

## Fuentes de datos
- **GESTIÓN CAMAS**: Registros de marcación de camas con fecha, servicio, cama, estado del flujo (Estado), estado de la cama (HCAESTADO), tiempos de cada paso, colaborador (NOMBRE_COMP) y cargo (carnombre). La consulta de origen no está documentada.

## Indicadores
- **Tiempo espera orientador**: Tiempo que la cama lleva esperando al orientador. Columna TIEMPO_ESPERA_ORIENTADOR; unidad por confirmar.
- **Tiempo espera SAMYL**: Tiempo que la cama lleva esperando a SAMYL. Columna TIEMPO_ESPERA_SAMYL; unidad por confirmar.
- **Tiempo desde aseo cama**: Tiempo transcurrido desde que la cama quedó aseada. Columna CAMA_ASEADA; unidad por confirmar.
- **Tiempo para acostar paciente**: Tiempo hasta que el paciente queda acostado en la cama. SUM(GESTIÓN CAMAS[PACIENTE_ACOSTADO]); eventos de inicio y fin y unidad por confirmar.

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
- **Sin documentación del propietario**: Esta página no tiene documento .docx; se describe solo a partir del PBIP local.
- **SAMYL**: El significado de SAMYL (posiblemente el equipo o proveedor de aseo) está por confirmar.
- **Unidades de tiempo**: Ninguna columna de tiempo indica si está en minutos u horas. Por confirmar.
- **Página homónima**: No confundir con DETALLE GESTIÓN CAMAS, que muestra capacidad y ocupación.
- **Acceso**: Por confirmar desde qué botón se llega; posiblemente desde el botón GESTIÓN DE CAMAS de DETALLE SOLICITUD CAMAS.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir del PBIP.
