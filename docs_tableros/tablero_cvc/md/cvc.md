---
tablero: TABLERO CVC
pagina: CVC
nombre_funcional: Aumentos y disminuciones de costo de compra por producto y mes
bloque: Histórico
tablas: [COSTOS_PRODUCTOS]
actualizado: 2026-10-20
version: 1
---

# CVC

## Propósito
Única página del tablero. Muestra cuántos productos se compraron, el valor comprado con aumento y con disminución de costo, la tendencia mensual de la variación de costos, la proporción de compras que subieron, bajaron o se mantuvieron, y el detalle por producto. Sirve para detectar alzas de precio y su impacto en las compras desde enero de 2025.

## Fuentes de datos
- **COSTOS_PRODUCTOS**: Registros de costo del almacén 062 desde 2025-01-01 con costo actual, costo anterior, cantidad y clasificación del producto.

## Indicadores
- **Total productos**: Número de productos o registros comprados según los filtros. Cálculo por confirmar.
- **Total compras con aumento**: Valor en pesos de las compras cuyo costo aumentó. Por confirmar si es la suma de COMPRA_TOTAL con ESTADO = "AUMENTÓ".
- **Total compras con disminución**: Valor en pesos de las compras cuyo costo disminuyó. Por confirmar si es la suma de COMPRA_TOTAL con ESTADO = "DISMINUYÓ".
- **Variación porcentual**: Cambio del costo actual frente al costo anterior. Columna variacion_porcent; si el costo anterior es 1 o menos usa el costo promedio (COSTOPROM) como base.
- **Variación frente al promedio anual**: Diferencia entre el costo actual y el precio promedio anual del producto, en pesos (VARIACION_PROM) y en proporción absoluta (VARIACION_POR_PROM).
- **Desviación de la tendencia de costos**: Valor mensual del gráfico TENDENCIA DE COSTOS, rotulado «Desviación estándar» en porcentaje. Cálculo por confirmar.

## Visuales
- **Tarjetas**: TOTAL PRODUCTOS, TOTAL COMPRAS CON AUMENTO y TOTAL COMPRAS CON DISMINUCIÓN.
- **Segmentadores**: Año, Mes, ESTADO, PRODUCTO y CLASIFICACION PRODUCTO.
- **Casillas**: DESABASTECIDO y PRODUCTO REGULADO; filtran los productos marcados con esa condición.
- **TENDENCIA DE COSTOS**: Línea por mes (2025 y 2026) con la desviación de costos en escala logarítmica de porcentaje.
- **Volatilidad de Costos por Mes y Año**: Torta con el número y porcentaje de registros AUMENTÓ, ESTABLE y DISMINUYÓ.
- **Tabla de productos**: CODIGO, PRODUCTO, CLASIFICACIÓN PRODUCTO, COSTO ANTERIOR, FECHA ANTERIOR, FECHA, CANTIDAD, COSTO ACTUAL, COMPRA TOTAL, variaciones y estado.

## Reglas de negocio
- **Columna ESTADO**: AUMENTÓ si el costo actual menos el anterior es mayor que 0, DISMINUYÓ si es menor que 0 y ESTABLE si es 0.
- **Columna COMPRA_TOTAL**: CANTIDAD multiplicada por ULTIMOCOSTO.

## Observaciones
- **Primera compra como aumento**: Si un producto no tiene costo anterior, la resta usa 0 y el registro queda como AUMENTÓ. Por confirmar si debería quedar sin estado.
- **Medidas del catálogo local**: El catálogo local tiene medidas inferidas que cuentan filas para las tarjetas de aumento y disminución, pero la captura muestra valores en pesos. No se usan esas medidas como fuente.
- **Total productos igual a aumentos**: En la captura, TOTAL PRODUCTOS (4.367) coincide con el número de registros AUMENTÓ del gráfico de volatilidad. Por confirmar qué cuenta la tarjeta.
- **Texto copiado**: La documentación describe los segmentadores como filtros de «citas asignadas»; es un error de copia.
- **Producto regulado**: La fuente de la marca PRODUCTO REGULADO no está documentada. Por confirmar.
- **Nombre de página**: La documentación no da el nombre de la página. Nombre de página en Power BI por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
