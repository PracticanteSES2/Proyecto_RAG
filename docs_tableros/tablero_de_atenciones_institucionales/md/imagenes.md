---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: IMAGENES
nombre_funcional: Imágenes diagnósticas realizadas por mes
bloque: Histórico
tablas: [CONSOLIDADO_IMAGENES_2025, Calendario, MostrarProyeccion]
actualizado: 2026-10-20
version: 1
---

# IMAGENES

## Propósito
Muestra cuántas imágenes diagnósticas se realizan cada mes, compara los años y proyecta el año en curso, con el total anual y el promedio mensual. Se llega con el botón IMAGENES de INICIO y desde aquí se abre AREA DE SERVICIO IMAGENES. Página oculta en modo lectura.

## Fuentes de datos
- **CONSOLIDADO_IMAGENES_2025**: Vista CONSOLIDADO_IMAGENES_DWSES con cédula, cantidad, entidad, fecha, código y nombre del examen, área de servicio, grupo, tipo de ingreso, valor facturado e ingreso, más la edad del paciente a la fecha del examen y la columna MAYORES (grupo de edad). Se une al Calendario por FECHA.

## Indicadores
- **Total de imágenes**: Suma de CANTIDAD del año elegido o, sin año elegido, del año cerrado. Medidas CANTIDAD_IMAGENES y TOTAL_ESTUDIOS.
- **Promedio de imágenes**: Total del año dividido entre 12; con varios años elegidos suma los promedios de cada año. Medida PROM_IMAGENES.
- **Imágenes por año fijo**: Cálculo: IMG_2025 = CALCULATE([IMAGENES], Calendario[Año] = 2025), con IMAGENES = SUM(CONSOLIDADO_IMAGENES_2025[CANTIDAD]); igual para 2024 y 2026.
- **Proyección de imágenes**: Medida PROYECCION_IMGA: para cada mes, imágenes del año anterior × (1 + crecimiento entre los dos años anteriores); solo con PROYECCION = SI y año 2025 o 2026 (sin año elegido toma 2026).

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes y TIPO INGRESO.
- **Casilla de proyección**: «PROYECCION» con la opción SI.
- **Botones de grupo de edad**: MAYORES DE EDAD y MENORES DE EDAD.
- **Gráfico de imágenes por mes**: Líneas «TOTAL DE IMÁGENES POR AÑO» con las imágenes por mes, una línea por año y una de PROYECCION.
- **Tarjetas de imágenes**: «PROMEDIO IMÁGENES» y «TOTAL ANUAL DE IMÁGENES».
- **Tabla de detalle**: Matriz de imágenes por año (filas) y mes (columnas).
- **Botón Detalle Apoyo Diagnóstico**: Abre AREA DE SERVICIO IMAGENES; el botón de casa vuelve a INICIO.

## Reglas de negocio
- **Unidad de conteo**: Se suma la columna CANTIDAD (estudios), no se cuentan filas.
- **Año por defecto**: Sin año elegido, total y promedio muestran el año cerrado y respetan el mes elegido.
- **Grupo de edad**: MENORES DE EDAD si la edad a la fecha del examen es menor de 18 años.

## Observaciones
- **Nombre de página**: IMAGENES según el PBIP; el PBIP solo trae page.json sin visuales.
- **TOTAL_ESTUDIOS distinto**: La documentación define TOTAL_ESTUDIOS con COUNTROWS (filas); en el modelo suma CANTIDAD.
- **IMG_2023 con error**: La documentación define IMG_2023 sobre [ATE_IMAGENES], medida que no existe; en el modelo usa [IMAGENES].
- **Proyección distinta al modelo**: La documentación toma el mes con MAX(Calendario[Mes]); el modelo calcula mes a mes. Ambas solo funcionan para 2025 y 2026.
- **Título del gráfico**: Se titula «TOTAL DE IMÁGENES POR AÑO» aunque el eje es mensual.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
