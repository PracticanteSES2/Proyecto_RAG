---
tablero: ASIGNACION DE CITAS
pagina: MAPA DE CALOR ASESORES
nombre_funcional: Gestiones de solicitudes por asesor y tramo horario
bloque: Histórico
tablas: [EN_ESPERA, ASESORES, Calendario]
actualizado: 2026-10-28
version: 2
---

# MAPA DE CALOR ASESORES

## Propósito
Mapa de calor con las gestiones de solicitudes de cita que registra cada asesor en cada media hora del día. Sirve para ver en qué horarios trabaja más cada asesor y el volumen total de gestiones. Se llega desde el botón MAPA DE CALOR ASESORES de INICIO. Análisis por año, mes y día (bloque Histórico).

## Fuentes de datos
- **EN_ESPERA**: Solicitudes con el asesor que registró su estado actual y el tramo horario de ese registro.
- **ASESORES**: Limita la página a usuarios con rol CITAS.

## Indicadores
- **Total gestiones**: Solicitudes gestionadas. DISTINCTCOUNT(EN_ESPERA[OID_CITA]).
- **Gestiones por asesor y tramo**: DISTINCTCOUNT(EN_ESPERA[OID_CITA]) por EN_ESPERA[ASESOR] y EN_ESPERA[TramoHorario].

## Visuales
- **Filtros de la página**: Segmentadores «Date Año», «Date Mes» y «Date Día» (año, mes y día), ASESOR (EN_ESPERA[NOMBRE_USUARIO]), ESPECIALIDAD y ASEGURADORA (EN_ESPERA[NOM_TERCERO]).
- **Tarjeta total gestiones**: Conteo total de gestiones con los filtros aplicados.
- **Mapa de calor por asesor**: Matriz con un asesor por fila, TRAMO HORARIO en columnas y el conteo de solicitudes en cada celda.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Solo asesores de citas**: Filtro de página ASESORES[ASESOR] distinto de vacío y de «.».
- **Colores del mapa**: Degradado de tres colores sobre el conteo: verde en el mínimo, amarillo en el punto medio y rojo en el máximo; las celdas vacías cuentan como cero.
- **Tramo horario**: Hora del registro redondeada hacia abajo a la media hora, en formato de 12 horas.

## Observaciones
- **Filtro ajeno en la tarjeta**: La tarjeta TOTAL GESTIONES tiene un filtro CITAS_ASIGNADAS[CCMESTADO] = 1 que no es de la tabla que cuenta; solo actúa a través de la relación bidireccional con ASEGURADORA. Por confirmar si es intencional.
- **Sin filtro de estado**: Ni la tarjeta ni el mapa filtran EN_ESPERA[CCEESTADO]; cuentan solicitudes en espera, asignadas y eliminadas.
- **Formato condicional huérfano**: La matriz conserva una regla de color sobre una tabla CITAS_EN_ESPERA que ya no existe en el modelo.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
