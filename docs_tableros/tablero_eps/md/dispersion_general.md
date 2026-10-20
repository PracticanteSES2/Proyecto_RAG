---
tablero: TABLERO EPS
pagina: DISPERSIÓN GENERAL
nombre_funcional: Atendidos frente a llegadas por tramo horario (histórico)
bloque: Histórico
tablas: [DISPERSION_GENERAL, ATENCIONES_ADMISIONES]
actualizado: 2026-10-20
version: 1
---

# DISPERSIÓN GENERAL

## Propósito
Gráfico de dispersión que compara, por tramo horario, los pacientes atendidos en triage con las llegadas a urgencias, para detectar horas con demanda mayor que la capacidad de atención. Es histórica (desde 2022) y se puede animar mes a mes. Se llega con el botón GRÁFICO DE DISPERSIÓN de % ATENCIONES / ADMISIONES.

## Fuentes de datos
- **Consulta de admisiones triage**: Todos los registros de ADMISIONTRIAGE (llegadas) desde el 2022-01-01 hasta hoy, con la fecha de entrada (HoraEntrada).
- **Consulta de triages**: Triages desde el 2022-01-01 con tramo horario y aseguradora; excluye la clasificación UA.

## Indicadores
- **Atendidos por tramo**: Cantidad de triages realizados en cada hora del día. Unidad: pacientes. Agregación por confirmar (conteo de triages).
- **Llegadas por tramo**: Cantidad de llegadas registradas en ADMISIONTRIAGE en cada hora del día. Unidad: pacientes. Agregación por confirmar (conteo de registros).

## Visuales
- **Filtros de segmentación**: Listas de Año, Mes, Día y ASEGURADORA.
- **Dispersión atendidos y llegadas por tramo**: Titulado «ATENDIDOS y LLEGADAS por TRAMO»; eje X ATENDIDOS, eje Y LLEGADAS y un punto de color por tramo horario (leyenda TRAMO).
- **Líneas guía**: Dos líneas rojas punteadas, una vertical y una horizontal, que dividen el gráfico en cuadrantes para ver qué tramos quedan por encima o por debajo del punto de equilibrio.
- **Control de reproducción por mes**: Botones de reproducir, pausar, detener y avanzar que animan el gráfico mes a mes.
- **Botón VOLVER**: Regresa a la página anterior.

## Reglas de negocio
- **Tramo horario**: La hora de llegada y la de triage se truncan a la hora en punto.
- **Lectura de cuadrantes**: Un tramo con muchas llegadas y pocos atendidos (arriba a la izquierda) indica demanda no atendida a tiempo.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Valor de las líneas guía**: Por confirmar si las líneas rojas marcan el promedio, la mediana u otro valor de atendidos y llegadas.
- **Llegadas sin filtro de aseguradora**: La consulta de ADMISIONTRIAGE no trae aseguradora en la documentación; por confirmar cómo responde el eje de llegadas al filtro ASEGURADORA.
- **Tabla del modelo**: En el catálogo local la tabla DISPERSION_GENERAL solo muestra la columna FECHA; su estructura real está por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
