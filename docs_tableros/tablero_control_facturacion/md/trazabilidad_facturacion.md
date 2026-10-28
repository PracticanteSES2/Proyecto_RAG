---
tablero: TABLERO CONTROL FACTURACION
pagina: TRAZABILIDAD FACTURACION
nombre_funcional: Valor estimado de los ingresos abiertos por fase, aseguradora y área de servicio
bloque: Día
tablas: [ULT_GESTION, CALENDARIO, DIM_TIPO_INGRESO]
actualizado: 2026-10-28
version: 1
---

# TRAZABILIDAD FACTURACION

## Propósito
Muestra el valor estimado de los servicios de los ingresos abiertos por fase (perfil), aseguradora y área de servicio, separado en ambulatorio y hospitalario, con filtros de año y mes de ingreso. Los gráficos se titulan «MONTO FACTURADO», pero suman ULT_GESTION[FACTURADO], que es el valor de los servicios cargados y no lo facturado. Página oculta en Power BI; ningún botón lleva a ella y su botón de inicio vuelve a INICIO.

## Fuentes de datos
- **ULT_GESTION**: Una fila por ingreso abierto con su última gestión; FECHA (fecha de ingreso) la relaciona con el calendario. Sin límite de fechas.

## Indicadores
- **Valor estimado**: Suma de ULT_GESTION[FACTURADO] en pesos, la tarjeta «Suma de FACTURADO»; es el valor de los servicios cargados a los ingresos abiertos, facturados o no.

## Visuales
- **Filtros**: Segmentadores «AREA SERVICIO» (ULT_GESTION[AREA_SERVICIO], sin vacíos), «Date Año» y «Date Mes» (CALENDARIO[Date], fecha de ingreso) y «TIPO_INGRESO» (DIM_TIPO_INGRESO[TIPO_INGRESO]); botón de inicio que vuelve a INICIO.
- **Tarjeta**: «Suma de FACTURADO»: suma de ULT_GESTION[FACTURADO] en el contexto.
- **Gráfico por fase**: Gráfico de líneas «MONTO FACTURADO POR FASE»; valor estimado por PERFIL (fase del proceso) con una serie por tipo de ingreso.
- **Barras por aseguradora**: Gráfico de barras agrupadas «MONTO FACTURADO POR ASEGURADORA»; valor estimado por ENTIDAD y tipo de ingreso, de mayor a menor.
- **Barras por área de servicio**: Gráfico de barras agrupadas «MONTO FACTURADO POR ÁREA DE SERVICIO»; valor estimado por AREA_SERVICIO y tipo de ingreso, de mayor a menor.

## Reglas de negocio
- **Sin filtros de página**: No filtra AINESTADO ni PERFIL (confirmado en el PBIP); aplican las exclusiones de ULT_GESTION: ingresos con estado 1, 2 o 4 y cuentas ya radicadas no están en la tabla.

## Observaciones
- **Títulos engañosos**: Los gráficos dicen «MONTO FACTURADO» pero la serie de aseguradora se rotula VALOR ESTIMADO y todas suman ULT_GESTION[FACTURADO]. El monto realmente facturado está en ULT_GESTION[MONTO_FACTURADO].
- **Sin botón de entrada**: Ningún botón del PBIP lleva a esta página. Por confirmar si sigue en uso.

## Historial de cambios
- **2026-10-28 · v1**: Página documentada a partir del modelo y del informe.
