---
tablero: TABLERO FARMACIA
pagina: TIEMPO DE DISPENSACIÓN
nombre_funcional: Evolución mensual de la oportunidad de dispensación
bloque: Histórico
tablas: [TIEMPOS_DISPENSACIÓN]
actualizado: 2026-10-20
version: 1
---

# TIEMPO DE DISPENSACIÓN

## Propósito
Sigue mes a mes el indicador de oportunidad de dispensación (tiempo promedio en horas para entregar medicamentos e insumos), con filtros por periodo, colaborador y servicio, para evaluar el cumplimiento de los tiempos. Análisis por año y mes (bloque Histórico). Se llega desde el botón TIEMPO DE DISPENSACIÓN de INICIO. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **TIEMPOS_DISPENSACIÓN**: Documentos de dispensación con colaborador, servicio, fecha del folio, fecha del documento y oportunidad en horas. Consulta no documentada.

## Indicadores
- **Oportunidad de dispensación**: Tiempo promedio de dispensación en horas. AVERAGE(TIEMPOS_DISPENSACIÓN[OportunidadHor]).

## Visuales
- **Filtros de la página**: Año y Mes de la fecha del documento (IDFECDOC), COLABORADOR (USUDESCRI, sin vacíos) y SERVICIO (gasnombre).
- **Línea de oportunidad por año y mes**: Titulado «OPORTUNIDAD DISPENSACIÓN por Año y Mes»; promedio de OportunidadHor por año y mes de la fecha del folio (hcfecfol).
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Unidad**: OportunidadHor está en horas según su nombre; entre qué eventos se mide está por confirmar.

## Observaciones
- **Fechas distintas**: Los filtros de año y mes usan la fecha del documento y el eje del gráfico la fecha del folio, así que un mes filtrado puede mostrar puntos de otros meses.
- **Tendencia llamativa**: En la captura la oportunidad baja de cerca de 700 horas en enero de 2025 a menos de 5 en octubre de 2026; por confirmar si refleja la operación o el cálculo.
- **Sin nombre en el PBIP**: La página existe en el PBIP sin archivo de página, por lo que su nombre en Power BI no se conoce.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
