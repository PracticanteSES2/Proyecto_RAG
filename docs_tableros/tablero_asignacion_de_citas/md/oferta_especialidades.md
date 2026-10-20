---
tablero: ASIGNACION DE CITAS
pagina: OFERTA ESPECIALIDADES
nombre_funcional: Demanda de citas: pendientes, asignadas, inasistencia y gestión por aseguradora
bloque: Histórico
tablas: [EN_ESPERA, CITAS_ASIGNADAS, ESPECIALIDADES, ASEGURADORA, Calendario]
actualizado: 2026-10-20
version: 1
---

# OFERTA ESPECIALIDADES

## Propósito
Reúne los indicadores de demanda de citas: solicitudes pendientes, citas asignadas, porcentaje de inasistencia y porcentaje pendiente, con su detalle por especialidad, día de la semana y aseguradora. Sirve para seguir la efectividad de la asignación. La documentación la llama «Demanda de citas»; se llega desde el botón DEMANDA DE CITAS de INICIO. Análisis por mes (bloque Histórico).

## Fuentes de datos
- **EN_ESPERA**: Solicitudes pendientes y gestionadas; la página excluye las eliminadas y las de estado vacío.
- **CITAS_ASIGNADAS**: Citas asignadas, inasistidas y canceladas.
- **ASEGURADORA**: Nombre del tercero (TERNOMCOM) para la tabla y el gráfico circular.

## Indicadores
- **Pendientes**: Solicitudes en espera sin ninguna gestión. SUM(EN_ESPERA[PENDIENTES_CO]).
- **Asignada**: Citas asignadas sin contar anuladas. SUM(CITAS_ASIGNADAS[Asignada]).
- **% inasistencia**: Proporción de citas inasistidas sobre asignadas. %INASISTENCIA = CALCULATE((sum(CITAS_ASIGNADAS[Inasistida])/sum(CITAS_ASIGNADAS[Asignada]))).
- **% pendiente**: Proporción de solicitudes en espera sobre citas asignadas. %PENDIENTE = CALCULATE((sum(EN_ESPERA[PENDIENTES])/sum(CITAS_ASIGNADAS[Asignada]))).
- **Inasistidas**: Citas en estado 3. SUM(CITAS_ASIGNADAS[Inasistida]).
- **Cancelada**: Citas en estado 1. SUM(CITAS_ASIGNADAS[Cancelada]).
- **Gestionada**: Solicitudes en estado asignada. SUM(EN_ESPERA[GESTIONADAS]).

## Visuales
- **Filtros de la página**: Lista de especialidades (ESPECIALIDADES[GEEDESCRI]) y botones de mes de Calendario.
- **Tarjetas de indicadores**: PENDIENTES, ASIGNADA, %INASISTENCIA y %PENDIENTE.
- **Columnas de pendientes por especialidad**: Titulado «PENDIENTES por ESPECIALIDAD»; SUM(PENDIENTES_CO) por especialidad, de mayor a menor.
- **Área de inasistidas por día**: Titulado «INASISTIDAS por DIA»; citas inasistidas por Calendario[DIA_SEMANA] de 1.LUNES a 7.DOMINGO.
- **Tabla de gestión por asegurador**: Una fila por ASEGURADOR (ASEGURADORA[TERNOMCOM]) con ASIGNADA, INASISTIDA, CANCELADA, GESTIONADA y PENDIENTE, con total.
- **Circular de pendientes por asegurador**: Titulado «PENDIENTES por ASEGURADOR»; reparto porcentual de PENDIENTES_CO por tercero.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Solicitudes consideradas**: Filtro de página EN_ESPERA[CCEESTADO] distinto de 2 (eliminada) y no vacío.
- **Pendiente sin gestión**: PENDIENTES_CO vale 1 si la solicitud está en espera y no tiene gestiones con estado distinto de 0.

## Observaciones
- **Numerador de % pendiente**: %PENDIENTE usa EN_ESPERA[PENDIENTES] (todas las solicitudes en espera) y no PENDIENTES_CO, que es lo que muestra la tarjeta PENDIENTES; las cifras no cuadran entre sí.
- **Día de las inasistencias**: Calendario se relaciona con CITAS_ASIGNADAS por fecha de asignación, así que INASISTIDAS por DIA agrupa por el día de la semana en que se asignó la cita, no el de la cita. Por confirmar si es intencional.
- **Nombre de la página**: En Power BI la página se llama OFERTA ESPECIALIDADES aunque el botón y la documentación dicen «Demanda de citas».

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
