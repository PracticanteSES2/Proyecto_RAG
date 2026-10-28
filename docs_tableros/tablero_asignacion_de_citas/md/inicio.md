---
tablero: ASIGNACION DE CITAS
pagina: INICIO
nombre_funcional: Resumen de solicitudes en espera, asignaciones y estados de las citas
bloque: Histórico
tablas: [EN_ESPERA, CITAS_ASIGNADAS, Calendario]
actualizado: 2026-10-28
version: 2
---

# INICIO

## Propósito
Página principal del tablero. Resume con tarjetas las solicitudes en espera, las asignadas, los días promedio para asignar y las citas asignadas, y muestra en un gráfico circular la distribución por estado. Tiene los botones que llevan a las otras diez páginas del tablero. Se analiza por año, mes y día (bloque Histórico).

## Fuentes de datos
- **EN_ESPERA**: Solicitudes de cita por especialidad; la página excluye las eliminadas (CCEESTADO = 2).
- **CITAS_ASIGNADAS**: Citas asignadas en Dinámica con su estado.

## Indicadores
- **Consultas en espera**: Solicitudes en estado en espera. DISTINCTCOUNT(EN_ESPERA[OID_CITA]) con CCEESTADO = 0.
- **Asignadas en espera**: Solicitudes de la lista de espera que ya tienen cita asignada. DISTINCTCOUNT(EN_ESPERA[OID_CITA]) con CCEESTADO = 1.
- **Total gestión cita en espera**: Solicitudes en espera más asignadas. DISTINCTCOUNT(EN_ESPERA[OID_CITA]) con CCEESTADO 0 o 1.
- **Días promedio para asignación**: Promedio en días entre el registro de la solicitud y la asignación de la cita. AVERAGE(EN_ESPERA[Tiempo_Asignacion]) con Tiempo_Asignacion >= 0.
- **Consultas asignadas**: Citas asignadas en el periodo, en cualquier estado. DISTINCTCOUNT(CITAS_ASIGNADAS[OID_CITA]).

## Visuales
- **Filtros de fecha**: Segmentadores de año, mes y día de Calendario («Date Año», «Date Mes» y «Date Día» de Calendario[Date]).
- **Tarjetas de indicadores**: Cinco tarjetas en la columna izquierda: CONSULTAS EN ESPERA, ASIGNADAS EN ESPERA, TOTAL GESTIÓN CITA EN ESPERA, DÍAS PROMEDIO PARA ASIGNACIÓN y CONSULTAS ASIGNADAS.
- **Gráfico circular de estados**: Conteo y porcentaje de EN ESPERA (SUM EN_ESPERA[PENDIENTES]), ASIGNADAS EN ESPERA (SUM EN_ESPERA[ASIGNADAS]), CITAS ASISTIDAS (SUM CONFIRMADO), CITAS REGISTRADAS (SUM REGISTRADO), CITAS CANCELADAS (SUM ANULADO) y CITAS INASISTIDAS (SUM CANCELADO). Filtro CCEESTADO 0 o 1.
- **Botones de navegación**: CONSULTAS POR ESPECIALIDAD, DETALLE EN ESPERA, ASIGNADAS POR ESPECIALIDAD, DETALLE ASIGNADAS, MAPA DE CALOR ASESORES, MAPA DE CALOR POR DÍA, DISPONIBILIDAD ESPECIALISTAS, COMPARATIVO CONSULTAS ASIGNADAS, ASIGNADAS POR ASESOR y DEMANDA DE CITAS.

## Reglas de negocio
- **Destino de los botones**: CONSULTAS POR ESPECIALIDAD abre EN ESPERA X ESPECIALIDAD; ASIGNADAS POR ESPECIALIDAD abre ASIGNADAS; MAPA DE CALOR POR DÍA abre MAPA DE CALOR X DIA; DISPONIBILIDAD ESPECIALISTAS abre DISPO X ESPECIALIDAD; COMPARATIVO CONSULTAS ASIGNADAS abre COMPARATIVO ASIGNADAS; ASIGNADAS POR ASESOR abre ASIGNADAS X ASESOR; DEMANDA DE CITAS abre OFERTA ESPECIALIDADES. Los demás abren la página del mismo nombre.
- **Estados en el gráfico circular**: Asistidas = estado 2, registradas = estado 0, canceladas = estado 1 e inasistidas = estado 3 de CITAS_ASIGNADAS[CCMESTADO].

## Observaciones
- **Fechas distintas en las tarjetas**: Las tarjetas de EN_ESPERA se filtran por fecha de registro de la solicitud y CONSULTAS ASIGNADAS por fecha de asignación de la cita.
- **Consultas asignadas incluye anuladas**: La tarjeta CONSULTAS ASIGNADAS no filtra el estado, por lo que cuenta también las citas anuladas. Por confirmar si es intencional.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
