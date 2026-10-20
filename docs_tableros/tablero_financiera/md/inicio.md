---
tablero: TABLERO FINANCIERA
pagina: INICIO
nombre_funcional: Resumen financiero del mes anterior y menú del tablero
bloque: Histórico
tablas: [FACTURACION, FACTURACION_PENDIENTE, REFACTURACION, FACTU_AREA, TERCEROS, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# INICIO

## Propósito
Página de entrada y única visible del tablero. Arriba muestra la facturación, los ingresos abiertos y las devoluciones del mes anterior; en el centro, la facturación mensual de 2025 y 2026 y la facturación neta por servicio; abajo, los aseguradores con mayor facturación neta y su participación. Una fila de botones lleva a las demás páginas.

## Fuentes de datos
- **FACTURACION**: Valor facturado de la tarjeta y medidas NETA, Facturacion_2025_Mensual y Facturacion_2026.
- **FACTURACION_PENDIENTE**: Valor de la tarjeta de ingresos abiertos.
- **REFACTURACION**: Valor de la tarjeta de devoluciones.
- **FACTU_AREA**: Servicio (CLASIFICACION_SERVICIO) del treemap.
- **TERCEROS**: Nombre comercial del asegurador (TERNOMCOM) del gráfico de aseguradores.
- **CALENDARIO**: Fecha para el filtro del mes anterior, jerarquía de año y mes, y medida NETA_AREA.

## Indicadores
- **Facturación del mes anterior**: Suma de FACTURACION[TOTALAREASERVORDEN] en el mes calendario anterior. Unidad: pesos.
- **Ingresos abiertos del mes anterior**: Suma de FACTURACION_PENDIENTE[VLSERVICIO] en el mes calendario anterior. Unidad: pesos.
- **Devoluciones del mes anterior**: Suma de REFACTURACION[VLRAREASERVICIO] en el mes calendario anterior. Unidad: pesos.
- **Facturación 2025 mensual**: Medida FACTURACION[Facturacion_2025_Mensual], facturación de cada mes de 2025. Unidad: pesos. Cálculo: Por confirmar.
- **Facturación 2026**: Medida FACTURACION[Facturacion_2026], facturación de cada mes de 2026. Unidad: pesos. Cálculo: Por confirmar.
- **Facturación neta por servicio**: Medida CALENDARIO[NETA_AREA], mostrada como FACTURACION NETA. Unidad: pesos. Cálculo: Por confirmar (parece facturación menos devoluciones por área).
- **Facturación neta por asegurador**: Medida FACTURACION[NETA], mostrada como FACTURACIÓN. Unidad: pesos. Cálculo: Por confirmar.
- **Participación del asegurador**: NETA del asegurador dividida por la NETA de todos los aseguradores del gráfico (cálculo del visual, %PARTICIPACIÓN). Unidad: porcentaje.

## Visuales
- **Tarjeta facturación**: Tarjeta FACTURACIÓN con el valor completo en pesos del mes anterior.
- **Tarjeta ingresos abiertos**: Tarjeta INGRESOS ABIERTOS con el valor completo en pesos del mes anterior.
- **Tarjeta devoluciones**: Tarjeta DEVOLUCIONES con el valor completo en pesos del mes anterior.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes (CALENDARIO), con selección múltiple, arriba a la derecha.
- **Botones de navegación**: Siete botones: FACTURACIÓN (abre Duplicado de Duplicado de FACTURACIÓN GENERAL), INGRESOS ABIERTOS (FACTURACION PENDIENTE), DEVOLUCIONES (REFACTURACION), FACTURACIÓN DIARIA (FACTURACION DIARIA), CUPS (CUPS), ANALISIS DE RENTABILIDAD (ANALISIS DE RENTABILIDAD) y CONSOLIDADO INGRESOS ABIERTOS (INGRESOS ABIERTOS ACTUAL).
- **Gráfico facturación 2025 y 2026**: Gráfico de líneas titulado «FACTURACIÓN 2025 Y 2026» con una línea para 2025 y otra para 2026 por mes, etiquetas en millones y una línea de promedio de 2026.
- **Treemap facturación neta por servicio**: Rectángulos por SERVICIO (FACTU_AREA[CLASIFICACION_SERVICIO]) cuyo tamaño es la FACTURACION NETA.
- **Gráfico de aseguradores**: Gráfico combinado con columnas de FACTURACIÓN (medida NETA) por ASEGURADOR (TERCEROS[TERNOMCOM]) de mayor a menor y una línea naranja con el %PARTICIPACIÓN.

## Reglas de negocio
- **Filtro mes anterior en tarjetas**: Las tres tarjetas filtran CALENDARIO[Date] al mes calendario anterior al día de consulta.
- **Tarjetas sin segmentadores**: Los segmentadores de año y mes no filtran las tarjetas; sí filtran el gráfico de líneas, el treemap y el gráfico de aseguradores.
- **Top de aseguradores**: El gráfico de aseguradores tiene un filtro Top N que deja los 10 TERCEROS[TERNOMCOM] con mayor FACTURACION[NETA].
- **Interacción entre gráficos**: Seleccionar un mes en el gráfico de líneas filtra el treemap y el gráfico de aseguradores; seleccionar un asegurador filtra el treemap pero no el gráfico de líneas.
- **Meses en blanco excluidos**: El gráfico de líneas y el de aseguradores excluyen los meses vacíos de la jerarquía de fechas.
- **Línea de promedio 2026**: El gráfico de líneas muestra el promedio de Facturacion_2026 como línea roja (#FF0505) con etiqueta en millones.

## Observaciones
- **Facturación bruta en la tarjeta**: La tarjeta FACTURACIÓN suma TOTALAREASERVORDEN sin restar devoluciones, mientras el gráfico de aseguradores, también titulado FACTURACIÓN, usa la medida neta NETA. Por confirmar cuál debe ver el usuario.
- **Participación entre los 10 primeros**: Por confirmar si el %PARTICIPACIÓN se calcula sobre los 10 aseguradores que muestra el gráfico o sobre todos.
- **Eje desde 2024**: El eje del gráfico de líneas empieza el 1 de enero de 2024 aunque solo tiene series de 2025 y 2026.
- **Sin acceso a COMPARATIVO**: No hay botón hacia COMPARATIVO, que parece una versión anterior de esta página.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
