---
tablero: TABLERO FINANCIERA
pagina: COMPARATIVO
nombre_funcional: Comparativo mensual de facturación neta, ingresos abiertos y devoluciones (versión anterior de INICIO)
bloque: Histórico
tablas: [FACTURACION_PENDIENTE, REFACTURACION, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# COMPARATIVO

## Propósito
Parece la versión anterior de INICIO: tarjetas del mes anterior con facturación neta, ingresos abiertos y devoluciones, botones a las páginas de detalle y un gráfico de área que compara las tres cifras por mes. Página oculta sin ningún botón que llegue a ella ni botón para volver a INICIO.

## Fuentes de datos
- **FACTURACION_PENDIENTE**: Ingresos abiertos: TOTAL_ING_ABIERTOS en la tarjeta y VLSERVICIO en el gráfico.
- **REFACTURACION**: Valor de devoluciones (VLRAREASERVICIO).
- **CALENDARIO**: Fecha del filtro del mes anterior, jerarquía de año y mes y medida FACTURACION_NETA.

## Indicadores
- **Facturación neta**: Medida CALENDARIO[FACTURACION_NETA], título FACTURACION, en la tarjeta (mes anterior) y en el gráfico. Unidad: pesos. Cálculo: Por confirmar.
- **Ingresos abiertos del mes anterior**: Suma de FACTURACION_PENDIENTE[TOTAL_ING_ABIERTOS] en el mes calendario anterior. Unidad: pesos.
- **Ingresos abiertos mensuales**: Suma de FACTURACION_PENDIENTE[VLSERVICIO] en el gráfico de área. Unidad: pesos.
- **Devoluciones**: Suma de REFACTURACION[VLRAREASERVICIO], en la tarjeta (mes anterior) y en el gráfico. Unidad: pesos.

## Visuales
- **Tarjetas del mes anterior**: Tres tarjetas FACTURACION, INGRESOS ABIERTOS y DEVOLUCIONES con el valor completo en pesos.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes con selección múltiple, arriba a la derecha.
- **Botones de navegación**: FACTURACIÓN (abre FACTURACIÓN GENERAL), INGRESOS ABIERTOS (FACTURACION PENDIENTE), DEVOLUCIONES (REFACTURACION) y FACTURACIÓN DIARIA (FACTURACION DIARIA).
- **Gráfico de área comparativo**: Gráfico de área con año y mes en el eje y tres series: FACTURACION, INGRESOS ABIERTOS y DEVOLUCIONES, en millones.

## Reglas de negocio
- **Filtro mes anterior en tarjetas**: Las tres tarjetas filtran CALENDARIO[Date] al mes calendario anterior al día de consulta.
- **Filtro de año del gráfico**: El gráfico de área tiene un filtro fijo de año igual a 2024 y excluye los meses vacíos.
- **Segmentadores y tarjetas**: El segmentador de mes no filtra ninguna tarjeta; el de año no filtra FACTURACION ni DEVOLUCIONES pero sí INGRESOS ABIERTOS.

## Observaciones
- **Página sin acceso**: Ningún botón lleva a esta página y no tiene botón de inicio. Por confirmar si se debe eliminar.
- **Ingresos abiertos con dos columnas**: La tarjeta usa TOTAL_ING_ABIERTOS y el gráfico VLSERVICIO (la tarjeta de INICIO usa VLSERVICIO). Por confirmar cuál es la correcta.
- **Gráfico fijo en 2024**: Por el filtro de año, el segmentador de año no puede mostrar otros años en el gráfico.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
