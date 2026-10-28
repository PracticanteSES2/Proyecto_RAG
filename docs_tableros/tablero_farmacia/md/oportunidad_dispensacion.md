---
tablero: TABLERO FARMACIA
pagina: OPORTUNIDAD DISPENSACIÓN
nombre_funcional: Evolución mensual de la oportunidad de dispensación
bloque: Histórico
tablas: [TIEMPOS_DISPENSACIÓN]
actualizado: 2026-10-28
version: 2
---

# OPORTUNIDAD DISPENSACIÓN

## Propósito
Sigue mes a mes el indicador de oportunidad de dispensación (tiempo promedio en horas entre el folio y el documento de suministro del medicamento), con filtros por periodo, colaborador y servicio, para evaluar el cumplimiento de los tiempos. Análisis por año y mes (bloque Histórico). Se llega desde el botón TIEMPO DE DISPENSACIÓN de INICIO; la página se llama OPORTUNIDAD DISPENSACIÓN en Power BI.

## Fuentes de datos
- **TIEMPOS_DISPENSACIÓN**: Una fila por orden de medicamento hospitalaria con su documento de suministro (folios desde 2025-01-01): colaborador, servicio, fecha del folio, fecha del documento y oportunidad en minutos y horas.

## Indicadores
- **Oportunidad de dispensación**: Tiempo promedio en horas entre la fecha del folio (hcfecfol) y la del documento de suministro (IDFECDOC), o hasta la consulta si no hay documento. AVERAGE(TIEMPOS_DISPENSACIÓN[OportunidadHor]).

## Visuales
- **Filtros de la página**: Segmentadores «IDFECDOC Año» e «IDFECDOC Mes» (año y mes de la fecha del documento IDFECDOC), COLABORADOR (USUDESCRI, sin vacíos) y SERVICIO (gasnombre).
- **Línea de oportunidad por año y mes**: Gráfico de líneas; eje año y mes de la fecha del folio (hcfecfol), valor AVERAGE(OportunidadHor) rotulado OPORTUNIDAD DISPENSACIÓN.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Unidad**: OportunidadHor está en horas enteras, entre hcfecfol y IDFECDOC; sin documento de suministro se mide hasta el momento de la consulta.

## Observaciones
- **Fechas distintas**: Los filtros de año y mes usan la fecha del documento y el eje del gráfico la fecha del folio, así que un mes filtrado puede mostrar puntos de otros meses.
- **Tendencia llamativa**: En la captura la oportunidad baja de cerca de 700 horas en enero de 2025 a menos de 5 en octubre de 2026. Posible causa: las órdenes sin documento de suministro siguen sumando horas hasta hoy y pesan más en los meses antiguos. Por confirmar.
- **Sin nombre en el PBIP**: El botón de INICIO se rotula TIEMPO DE DISPENSACIÓN, pero la página se llama OPORTUNIDAD DISPENSACIÓN en Power BI; está oculta en modo vista.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
