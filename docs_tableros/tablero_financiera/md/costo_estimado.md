---
tablero: TABLERO FINANCIERA
pagina: COSTO ESTIMADO
nombre_funcional: Rentabilidad por CUPS frente al costo histórico y al costo estimado
bloque: Histórico
tablas: [ANALISIS_RENTABILIDAD, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# COSTO ESTIMADO

## Propósito
Compara por CUPS y pagador la venta con el costo histórico y con el costo estimado, y muestra la rentabilidad frente a cada uno; abajo, venta, costo y rentabilidad por mes de 2024 y 2025. Es una página larga (1.600 píxeles de alto). Página oculta; se llega con el botón COSTO ESTIMADO de ANALISIS DE RENTABILIDAD y su botón de inicio vuelve a INICIO.

## Fuentes de datos
- **ANALISIS_RENTABILIDAD**: CUPS (ACTIVI), TERCERO, CENTROCOSTO, PERDIDA, frecuencia (CANT), venta unitaria (VLRMAXCUPS), costo histórico (COSTOHIST) y costo estimado (COSTOVARIACION).
- **CALENDARIO**: Jerarquía de año y mes y medidas Venta Total, Costo Total, Rentabilidad total, FRECUENCIA_TOTAL, rentabilidad_costo_ses y rentabilidad_costo_estimado.

## Indicadores
- **Venta total**: Medida CALENDARIO[Venta Total], tarjeta y columna Venta y gráfico Total Ventas. Unidad: pesos. Cálculo: Por confirmar.
- **Costo total**: Medida CALENDARIO[Costo Total], tarjeta Costo y gráfico Costo Total. Unidad: pesos. Cálculo: Por confirmar.
- **Rentabilidad total**: Medida CALENDARIO[Rentabilidad total], tarjeta y gráfico Rentabilidad. Unidad: pesos. Cálculo: Por confirmar.
- **Frecuencia**: Suma de ANALISIS_RENTABILIDAD[CANT], tarjeta Frecuencia. Unidad: cantidad de servicios.
- **Frecuencia total**: Medida CALENDARIO[FRECUENCIA_TOTAL], columna Frecuencia de la tabla. Unidad: cantidad de servicios. Cálculo: Por confirmar.
- **Venta unitaria**: Máximo de ANALISIS_RENTABILIDAD[VLRMAXCUPS], columna Venta Unitaria. Unidad: pesos.
- **Costo histórico**: Promedio de ANALISIS_RENTABILIDAD[COSTOHIST], columna Costo. Unidad: pesos.
- **Costo estimado**: Promedio de ANALISIS_RENTABILIDAD[COSTOVARIACION], columna Estimado. Unidad: pesos. Por confirmar cómo se estima.
- **Rentabilidad frente al costo**: Medida CALENDARIO[rentabilidad_costo_ses], columna Rentabilidad VS Costo. Unidad: pesos. Cálculo: Por confirmar.
- **Rentabilidad frente al estimado**: Medida CALENDARIO[rentabilidad_costo_estimado], columna Rentabilidad VS Estimado. Unidad: pesos. Cálculo: Por confirmar.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes; el de año no ofrece 2023.
- **Segmentadores de CUPS, centro de costos y pagador**: Listas desplegables CUPS (ACTIVI), Centro de Costos (CENTROCOSTO) y Pagador (TERCERO) de ANALISIS_RENTABILIDAD.
- **Segmentador pérdida**: Lista PERDIDA (ANALISIS_RENTABILIDAD[PERDIDA]) para separar los CUPS con pérdida.
- **Tarjetas de totales**: Cuatro tarjetas con el valor completo: Venta, Costo, Rentabilidad y Frecuencia.
- **Tabla costo estimado por CUPS**: Matriz con CUPS y TERCERO en filas y Frecuencia, Venta, Venta Unitaria, Costo, Estimado, Rentabilidad VS Costo y Rentabilidad VS Estimado.
- **Gráficos mensuales**: Tres gráficos de líneas por mes, con una línea por año: Total Ventas, Costo Total y Rentabilidad, con etiquetas en millones.

## Reglas de negocio
- **Barras de rentabilidad**: Rentabilidad VS Costo y Rentabilidad VS Estimado tienen barras de datos de -1.000.000 a 1.000.000: verde (#92D050) si es positiva y rojo (#C00000) si es negativa.
- **Gráficos 2024 y 2025**: Los tres gráficos mensuales filtran año 2024 y 2025.
- **Líneas de promedio**: Cada gráfico mensual tiene una línea de promedio roja (#C00000) con etiqueta en millones sin decimales.
- **Sin año 2023**: El segmentador de año oculta 2023 y los años vacíos.
- **Pérdida sin vacíos**: El segmentador PERDIDA excluye los valores vacíos.

## Observaciones
- **Gráficos sin 2026**: Por el filtro fijo de años, los gráficos no muestran 2026. Por confirmar si se debe actualizar.
- **Promedios sobre otras columnas**: Las líneas de promedio se definen sobre sumas de VLRSERVICIOENORDEN, TOTAL_COSTO y RENTABILIDAD_TOTAL, no sobre las medidas que se grafican. Por confirmar si se muestran.
- **Formato heredado**: La tabla guarda barras de datos para COSTOS[RENTABILIDAD] y COSTOS[%RENT], columnas que no están en el visual.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
