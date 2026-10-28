---
tablero: ASIGNACION DE CITAS
pagina: EN ESPERA X ESPECIALIDAD
nombre_funcional: Consultas en espera por especialidad y top 5 de aseguradoras
bloque: Histórico
tablas: [EN_ESPERA, ASEGURADORA, Calendario]
actualizado: 2026-10-28
version: 2
---

# EN ESPERA X ESPECIALIDAD

## Propósito
Muestra cuántas solicitudes de cita siguen en espera en cada especialidad y las 5 aseguradoras con más solicitudes en espera, para ver la carga de solicitudes por área. La documentación la llama «Consultas por especialidad»; se llega desde el botón CONSULTAS POR ESPECIALIDAD de INICIO. Análisis por año y mes de registro (bloque Histórico).

## Fuentes de datos
- **EN_ESPERA**: Solicitudes de cita; la página solo deja las que están en espera (CCEESTADO = 0).
- **ASEGURADORA**: Aporta el nombre homologado de la aseguradora (ASEGURADORA_HM) para el top 5.

## Indicadores
- **Consultas en espera**: Solicitudes en espera. DISTINCTCOUNT(EN_ESPERA[OID_CITA]).
- **Solicitudes por especialidad**: Solicitudes en espera de cada especialidad. DISTINCTCOUNT(EN_ESPERA[OID_CITA]) por EN_ESPERA[GEEDESCRI].
- **Consultas solicitadas por aseguradora**: Filas de solicitudes en espera por aseguradora. COUNT(EN_ESPERA[OID_CITA]) por ASEGURADORA[ASEGURADORA_HM].

## Visuales
- **Filtros de fecha**: Segmentadores de año y mes de Calendario («Date Año» y «Date Mes»; fecha de registro de la solicitud).
- **Filtro de clasificación**: Casillas por EN_ESPERA[MAESTROS]: MAGISTERIO, MEDICINA PREPAGADA, OTROS y PARTICULAR.
- **Filtro de aseguradora**: Segmentador «ASEGURADORA» con EN_ESPERA[NOM_TERCERO].
- **Tarjeta consultas en espera**: Total de solicitudes en espera con los filtros aplicados.
- **Barras de solicitudes por especialidad**: Barras horizontales con SOLICITUDES por ESPECIALIDAD, de mayor a menor.
- **Barras top 5 aseguradoras**: Titulado «TOP 5 ASEGURADORAS CON CITAS EN ESPERA»; CONSULTAS SOLICITADAS por aseguradora homologada, de mayor a menor.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Solo solicitudes en espera**: Filtro de página CCEESTADO = 0.
- **Top 5 de aseguradoras**: Filtro TopN que deja las 5 aseguradoras homologadas con más solicitudes y excluye la aseguradora vacía.

## Observaciones
- **Segmentador de mes repetido**: La página tiene dos segmentadores de mes de Calendario y ninguno de día; por confirmar si uno debía ser de día.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
