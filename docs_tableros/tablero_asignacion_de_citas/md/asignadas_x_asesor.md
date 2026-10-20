---
tablero: ASIGNACION DE CITAS
pagina: ASIGNADAS X ASESOR
nombre_funcional: Gestión de citas por asesor según estado
bloque: Histórico
tablas: [ASESORES, EN_ESPERA, CITAS_ASIGNADAS, ASEGURADORA, Calendario]
actualizado: 2026-10-20
version: 1
---

# ASIGNADAS X ASESOR

## Propósito
Muestra, para cada asesor del área de citas, cuántas solicitudes de la lista de espera asignó y cuántas de sus citas quedaron registradas, confirmadas, inasistidas o anuladas. Sirve para medir la gestión de cada asesor. La documentación la llama «Asignadas por asesor»; se llega desde el botón ASIGNADAS POR ASESOR de INICIO. Análisis por año, mes y día (bloque Histórico).

## Fuentes de datos
- **ASESORES**: Usuarios con rol CITAS; dan las filas de la tabla.
- **EN_ESPERA**: Solicitudes asignadas desde la lista de espera (la página filtra CCEESTADO = 1).
- **CITAS_ASIGNADAS**: Citas asignadas por cada asesor con su estado.

## Indicadores
- **Asignadas en espera**: Solicitudes de la lista de espera asignadas por el asesor. SUM(EN_ESPERA[ASIGNADAS]).
- **Asignadas**: Citas del asesor en estado registrada (0). SUM(CITAS_ASIGNADAS[REGISTRADO]).
- **Citas confirmadas**: Citas en estado confirmada (2). SUM(CITAS_ASIGNADAS[CONFIRMADO]).
- **Canceladas**: Citas en estado 3. SUM(CITAS_ASIGNADAS[CANCELADO]).
- **Anuladas**: Citas en estado 1. SUM(CITAS_ASIGNADAS[ANULADO]).

## Visuales
- **Filtros de la página**: Segmentadores de año, mes y día, ASESOR (EN_ESPERA[ASESOR]), ESPECIALIDAD (EN_ESPERA[GEEDESCRI]) y ASEGURADORA (ASEGURADORA[ASEGURADORA_HM]).
- **Tabla de gestión por asesor**: Una fila por asesor (ASESORES[ASESOR]) con ASIGNADAS EN ESPERA, ASIGNADAS, CITAS CONFIRMADAS, CANCELADAS y ANULADAS, y fila de total.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Solicitudes asignadas**: Filtro de página EN_ESPERA[CCEESTADO] = 1.
- **Asesor de la cita**: En CITAS_ASIGNADAS el asesor es el usuario que asignó la cita; en EN_ESPERA es el usuario que gestionó la solicitud.

## Observaciones
- **Canceladas son inasistidas**: La columna CANCELADAS suma el estado 3, que en INICIO se llama «CITAS INASISTIDAS»; ANULADAS suma el estado 1, que en INICIO se llama «CITAS CANCELADAS».
- **Fila sin asesor**: La tabla muestra una fila con asesor vacío; agruparía las gestiones de usuarios que no están en ASESORES (rol distinto de CITAS). Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
