---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: MAPA DE CALOR TRATAMIENTOS
nombre_funcional: Mapa de calor del tiempo para inicio de tratamiento
bloque: Histórico
tablas: [INICIO_TRAT_HIST]
actualizado: 2026-10-28
version: 2
---

# MAPA DE CALOR TRATAMIENTOS

## Propósito
Muestra el tiempo promedio para inicio de tratamiento por día de la semana y hora del ingreso por enfermería, con color de verde a rojo. Se llega desde INICIO TRATAMIENTO HISTORICOS.

## Fuentes de datos
- **INICIO_TRAT_HIST**: Ingresos desde el 01/01/2023 con primer folio en urgencias e ingreso por enfermería; FECHA es la fecha de admisión; tabla en Import.

## Indicadores
- **Tiempo promedio inicio tratamiento**: Minutos entre el primer folio en urgencias y el inicio de la estancia, por tramo horario y día de la semana. CALCULATE(AVERAGE(INICIO_TRAT_HIST[TIEMPO_INGRESO]), INICIO_TRAT_HIST[TIEMPO_INGRESO] < 241).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de admisión.
- **Mapa de calor de tratamientos**: Matriz con filas tramo horario del ingreso (TramoHorario_ING), columnas día de la semana (DIA_SEMANA_TRAT, sobre la fecha de admisión) y valor el promedio de TIEMPO_INGRESO. Filtro: TIEMPO_INGRESO menor que 241; su filtro sobre CONSULTA_URGENCIAS no tiene efecto.
- **Botón de regreso**: Lleva a INICIO TRATAMIENTO HISTORICOS.
- **Nombres de campos**: Nombres de los campos en el informe: segmentadores de Calendario[FECHA] «Date Mes», «Date Día».

## Reglas de negocio
- **Color del mapa de calor**: Degradado verde, amarillo y rojo relativo a los valores mostrados.
- **Límite de 4 horas**: Se excluyen los tiempos de 241 minutos o más.

## Observaciones
- **Orden del tramo horario**: TramoHorario_ING es texto; las filas pueden ordenarse alfabéticamente (por ejemplo «01:00 p. m.» junto a «01:00 a. m.»). Se recomienda cargarla como hora o agregar una columna de orden.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
