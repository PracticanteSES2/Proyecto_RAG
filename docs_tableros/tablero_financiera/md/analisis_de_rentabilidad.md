---
tablero: TABLERO FINANCIERA
pagina: ANALISIS DE RENTABILIDAD
nombre_funcional: Venta, costo y rentabilidad por CUPS
bloque: Histórico
tablas: [ANALISIS_RENTABILIDAD, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# ANALISIS DE RENTABILIDAD

## Propósito
Muestra la venta, el costo y la rentabilidad por CUPS: tarjetas de totales, una tabla por CUPS y tres gráficos mensuales que comparan años. Es una página larga (1.650 píxeles de alto) que se recorre con desplazamiento. Página oculta; se llega con el botón ANALISIS DE RENTABILIDAD de INICIO y al final tiene el botón COSTO ESTIMADO.

## Fuentes de datos
- **ANALISIS_RENTABILIDAD**: CUPS (ACTIVI), CENTROCOSTO, TERCERO, PERDIDA, frecuencia (CANT), venta unitaria (VLRMAXCUPS) y costo histórico (COSTOHIST).
- **CALENDARIO**: Jerarquía de año y mes y medidas Venta Total, Costo Total, Rentabilidad total, FRECUENCIA_TOTAL, venta_uni y %RENTABILIDAD.

## Indicadores
- **Venta total**: Medida CALENDARIO[Venta Total], tarjeta Venta y gráfico Total Venta. Unidad: pesos. Cálculo: Por confirmar.
- **Costo total**: Medida CALENDARIO[Costo Total], tarjeta Costo y gráfico Costo Total. Unidad: pesos. Cálculo: Por confirmar.
- **Rentabilidad total**: Medida CALENDARIO[Rentabilidad total], tarjeta y gráfico Rentabilidad. Unidad: pesos. Cálculo: Por confirmar.
- **Frecuencia**: Suma de ANALISIS_RENTABILIDAD[CANT], tarjeta Frecuencia. Unidad: cantidad de servicios.
- **Frecuencia total**: Medida CALENDARIO[FRECUENCIA_TOTAL], columna Fcia de la tabla. Unidad: cantidad de servicios. Cálculo: Por confirmar.
- **Venta unitaria**: Máximo de ANALISIS_RENTABILIDAD[VLRMAXCUPS], columna Venta de la tabla. Unidad: pesos.
- **Costo unitario histórico**: Promedio de ANALISIS_RENTABILIDAD[COSTOHIST], columna Costo de la tabla. Unidad: pesos.
- **Rentabilidad unitaria**: Medida CALENDARIO[venta_uni], columna Rentabilidad de la tabla. Unidad y cálculo: Por confirmar (sus barras de datos van de -1 a 1, como un porcentaje).
- **Porcentaje de rentabilidad**: Medida CALENDARIO[%RENTABILIDAD], columna % de la tabla. Unidad: porcentaje. Cálculo: Por confirmar.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes; el de año no ofrece 2023.
- **Segmentadores de CUPS, centro de costos y pagador**: Listas desplegables CUPS (ACTIVI), Centro de Costos (CENTROCOSTO) y Pagador (TERCERO) de ANALISIS_RENTABILIDAD.
- **Segmentador pérdida**: Lista PERDIDA (ANALISIS_RENTABILIDAD[PERDIDA]) para separar los CUPS con pérdida.
- **Tarjetas de totales**: Cuatro tarjetas con el valor completo: Venta, Costo, Rentabilidad y Frecuencia.
- **Tabla rentabilidad por CUPS**: Matriz con CUPS en filas y las columnas Fcia, Venta, Costo, Rentabilidad y %, ordenada por CUPS, sin subtotales de fila.
- **Gráfico venta mensual**: Gráfico de líneas de Total Venta por mes, con una línea por año y etiquetas en millones.
- **Gráfico costo mensual**: Gráfico de líneas de Costo Total por mes, con una línea por año y etiquetas en millones.
- **Gráfico rentabilidad mensual**: Gráfico de líneas de Rentabilidad por mes, con una línea por año y etiquetas en millones.
- **Botón costo estimado**: Botón COSTO ESTIMADO al final de la página que abre COSTO ESTIMADO.

## Reglas de negocio
- **Barras de rentabilidad**: La columna Rentabilidad (venta_uni) tiene barras de datos de -1 a 1: verde (#48F579) si es positiva y rojo (#F65B40) si es negativa.
- **Líneas de promedio**: Cada gráfico mensual tiene una línea de promedio roja (#C00000) con etiqueta en millones sin decimales.
- **Sin año 2023**: El segmentador de año oculta 2023 y los años vacíos.
- **Pérdida sin vacíos**: El segmentador PERDIDA excluye los valores vacíos.

## Observaciones
- **Promedios sobre otras columnas**: Las líneas de promedio se definen sobre sumas de VLRSERVICIOENORDEN, TOTAL_COSTO y RENTABILIDAD_TOTAL, no sobre las medidas que se grafican. Por confirmar si se muestran.
- **Formato heredado**: La tabla guarda barras de datos para COSTOS[RENTABILIDAD] y COSTOS[%RENT], columnas que no están en el visual (restos de COSTOS ANTERIOR).
- **Unitarios frente a totales**: La tabla muestra la venta máxima y el costo promedio por CUPS, mientras las tarjetas muestran totales.
- **Valores de PERDIDA**: Los valores del segmentador PERDIDA están por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
