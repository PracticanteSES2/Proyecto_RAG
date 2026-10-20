---
tablero: ASIGNACION DE CITAS
pagina: ASIGNADAS
nombre_funcional: Solicitudes asignadas por especialidad y top 5 de aseguradoras
bloque: Histórico
tablas: [EN_ESPERA, ASEGURADORA, Calendario]
actualizado: 2026-10-20
version: 1
---

# ASIGNADAS

## Propósito
Muestra las solicitudes de la lista de espera que ya quedaron asignadas, por especialidad, y las 5 aseguradoras con más asignaciones. Sirve para ver qué especialidades concentran la gestión de asignación. La documentación la llama «Asignadas por especialidad»; se llega desde el botón ASIGNADAS POR ESPECIALIDAD de INICIO. Análisis por año, mes y día de registro (bloque Histórico).

## Fuentes de datos
- **EN_ESPERA**: Solicitudes de cita; la página solo deja las asignadas (CCEESTADO = 1).
- **ASEGURADORA**: Aporta el nombre homologado (ASEGURADORA_HM) para el top 5.

## Indicadores
- **Consultas asignadas**: Solicitudes en estado asignada. DISTINCTCOUNT(EN_ESPERA[OID_CITA]).
- **Asignadas por especialidad**: DISTINCTCOUNT(EN_ESPERA[OID_CITA]) por EN_ESPERA[GEEDESCRI].
- **Asignadas por aseguradora**: SUM(EN_ESPERA[ASIGNADAS]) por ASEGURADORA[ASEGURADORA_HM]; ASIGNADAS vale 1 cuando CCEESTADO = 1.

## Visuales
- **Filtros de fecha**: Segmentadores de año, mes y día de Calendario (fecha de registro de la solicitud).
- **Filtro de aseguradora**: Segmentador «ASEGURADORA» con EN_ESPERA[NOM_TERCERO].
- **Filtro de clasificación**: Casillas por EN_ESPERA[MAESTROS] (MAGISTERIO, MEDICINA PREPAGADA, OTROS, PARTICULAR).
- **Tarjeta consultas asignadas**: Total de solicitudes asignadas con los filtros aplicados.
- **Barras de asignadas por especialidad**: Barras horizontales con ASIGNADAS por ESPECIALIDAD, de mayor a menor.
- **Barras top 5 aseguradoras**: Titulado «TOP 5 ASEGURADORAS CON CITAS ASIGNADAS»; CONSULTAS ASIGNADAS por aseguradora homologada.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Solo solicitudes asignadas**: Filtro de página CCEESTADO = 1.
- **Top 5 de aseguradoras**: Filtro TopN de 5 aseguradoras homologadas; excluye la aseguradora vacía.

## Observaciones
- **Mismo nombre, otra medida**: La tarjeta «CONSULTAS ASIGNADAS» de esta página cuenta solicitudes asignadas de EN_ESPERA; la de INICIO con el mismo nombre cuenta citas de CITAS_ASIGNADAS. Las cifras no son comparables.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
