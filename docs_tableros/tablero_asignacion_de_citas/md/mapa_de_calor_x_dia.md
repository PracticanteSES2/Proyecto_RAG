---
tablero: ASIGNACION DE CITAS
pagina: MAPA DE CALOR X DIA
nombre_funcional: Gestiones de solicitudes por día de la semana y tramo horario
bloque: Histórico
tablas: [EN_ESPERA, ASESORES, Calendario]
actualizado: 2026-10-20
version: 1
---

# MAPA DE CALOR X DIA

## Propósito
Mapa de calor con las gestiones de solicitudes de cita por día de la semana y media hora del día. Sirve para ver los horarios y días de mayor carga en el área de citas. La documentación la llama «Mapa de calor por día»; se llega desde el botón MAPA DE CALOR POR DÍA de INICIO. Análisis por año, mes y día (bloque Histórico).

## Fuentes de datos
- **EN_ESPERA**: Solicitudes con día de la semana y tramo horario del registro de su estado actual.
- **ASESORES**: Limita la página a usuarios con rol CITAS.

## Indicadores
- **Total gestiones**: Filas de solicitudes gestionadas. COUNT(EN_ESPERA[OID_CITA]).
- **Gestiones por día y tramo**: DISTINCTCOUNT(EN_ESPERA[OID_CITA]) por EN_ESPERA[DIA_SEMANA] y EN_ESPERA[TramoHorario].

## Visuales
- **Filtros de la página**: Segmentadores de año, mes y día, ESPECIALIDAD, ASEGURADORA (EN_ESPERA[NOM_TERCERO]) y una lista de asesores (EN_ESPERA[ASESOR]) al lado de la matriz.
- **Tarjeta total gestiones**: Conteo total de gestiones con los filtros aplicados.
- **Mapa de calor por día**: Matriz con TRAMO HORARIO en filas (orden ascendente), DÍA SEMANA en columnas (1. LUNES a 7. DOMINGO) y el conteo de solicitudes en cada celda.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Solo asesores de citas**: Filtro de página ASESORES[ASESOR] distinto de vacío y de «.».
- **Colores del mapa**: Degradado de tres colores sobre el conteo: verde en el mínimo, amarillo en el punto medio y rojo en el máximo; las celdas vacías cuentan como cero.
- **Día de la semana**: Se calcula en SQL desde la fecha de registro del estado de la solicitud, numerado de 1. LUNES a 7. DOMINGO.

## Observaciones
- **Conteo distinto entre tarjetas**: Aquí TOTAL GESTIONES usa COUNT y en MAPA DE CALOR ASESORES usa DISTINCTCOUNT; con una fila por solicitud el resultado coincide.
- **Filtro ajeno en la tarjeta**: La tarjeta tiene un filtro CITAS_ASIGNADAS[CCMESTADO] = 1 que solo actúa a través de la relación con ASEGURADORA. Por confirmar si es intencional.
- **Filtro de estado anunciado**: La documentación menciona un filtro por estado que no existe en el PBIP.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
