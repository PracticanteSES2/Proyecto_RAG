---
tablero: TABLERO EPS
pagina: DISPERSION GENERAL
nombre_funcional: Atendidos frente a llegadas por tramo horario (histórico)
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE, ADMISIONES_TRIAGE, Calendario]
actualizado: 2026-10-28
version: 2
---

# DISPERSION GENERAL

## Propósito
Gráfico de dispersión «ATENDIDOS y LLEGADAS por TRAMO» que compara, por tramo horario, los pacientes atendidos en triage con las llegadas a urgencias, para detectar horas con demanda mayor que la capacidad de atención. Es histórica (desde 2022) y se puede animar mes a mes. Se llega con el botón GRÁFICO DE DISPERSIÓN de %ATENCIONES/ADMISIONES.

## Fuentes de datos
- **ADMISIONES_TRIAGE**: Todos los registros de ADMISIONTRIAGE (llegadas) desde el 2022-01-01 hasta hoy, con la fecha de entrada (HoraEntrada).
- **OPORTUNIDAD_TRIAGE**: Triages desde el 2022-01-01 con tramo horario y aseguradora; excluye la clasificación UA.

## Indicadores
- **Atendidos por tramo**: Cantidad de triages realizados en cada hora del día. Unidad: pacientes. DISTINCTCOUNT de OPORTUNIDAD_TRIAGE[OID_TRIAGE] por TramoHorario.
- **Llegadas por tramo**: Cantidad de llegadas registradas en ADMISIONTRIAGE en cada hora del día. Unidad: pacientes. DISTINCTCOUNT de ADMISIONES_TRIAGE[Oid]; se cruza con los triages por documento del paciente.

## Visuales
- **Filtros de segmentación**: Listas de Año, Mes y Día (segmentadores «Fecha Año», «Fecha Mes» y «Fecha Día» de Calendario[Fecha]) y ASEGURADORA.
- **Dispersión atendidos y llegadas por tramo**: Titulado «ATENDIDOS y LLEGADAS por TRAMO»; eje X ATENDIDOS, eje Y LLEGADAS y un punto de color por tramo horario (leyenda TRAMO).
- **Líneas guía**: Dos líneas rojas punteadas, una vertical y una horizontal, que dividen el gráfico en cuadrantes para ver qué tramos quedan por encima o por debajo del punto de equilibrio.
- **Control de reproducción por mes**: Botones de reproducir, pausar, detener y avanzar que animan el gráfico mes a mes.
- **Botón VOLVER**: Regresa a la página anterior.

## Reglas de negocio
- **Tramo horario**: La hora de llegada y la de triage se truncan a la hora en punto.
- **Lectura de cuadrantes**: Un tramo con muchas llegadas y pocos atendidos (arriba a la izquierda) indica demanda no atendida a tiempo.

## Observaciones
- **Valor de las líneas guía**: Por confirmar si las líneas rojas marcan el promedio, la mediana u otro valor de atendidos y llegadas.
- **Llegadas y aseguradora**: ADMISIONES_TRIAGE no trae aseguradora; el eje de llegadas responde al filtro ASEGURADORA solo por el cruce de documento con los triages.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
