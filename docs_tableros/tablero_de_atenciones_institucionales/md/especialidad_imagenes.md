---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: ESPECIALIDAD IMAGENES
nombre_funcional: Imágenes diagnósticas por área de servicio
bloque: Histórico
tablas: [CONSOLIDADO_IMAGENES_2025, Calendario]
actualizado: 2026-10-28
version: 2
---

# ESPECIALIDAD IMAGENES

## Propósito
Muestra cuántas imágenes diagnósticas se realizan en cada área (rayos X, escanografía, ecografía, resonancia, etc.), con el total y el promedio mensual. Se llega con el botón DETALLE APOYO DIAGNOSTICO de la página IMAGENES.

## Fuentes de datos
- **CONSOLIDADO_IMAGENES_2025**: La misma tabla de la página IMAGENES; el área sale de la columna AREA_SERVICIO.

## Indicadores
- **Total de imágenes**: Suma de CANTIDAD del año elegido o, sin año elegido, del año cerrado. Medida CANTIDAD_IMAGENES o TOTAL_ESTUDIOS (por confirmar cuál usa la tarjeta).
- **Promedio de imágenes**: Total del año dividido entre 12. Medida PROM_IMAGENES.
- **Imágenes por área**: Suma de CANTIDAD por AREA_SERVICIO.

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes y TIPO INGRESO.
- **Botones de grupo de edad**: MAYORES DE EDAD y MENORES DE EDAD.
- **Mapa de árbol por área**: «CANTIDAD IMAGENES POR AREA SERVICIO» con un recuadro por área (RAYOS X, ESCANOGRAFIA, ECOGRAFIA, RESONANCIA MAGNETICA, CARDIOLOGIA, MAMOGRAFIA, GASTRO, MEDICINA NUCLEAR) proporcional a su cantidad.
- **Tarjetas de imágenes**: «TOTAL IMAGENES» y «PROMEDIO IMAGENES».
- **Tabla de detalle anual**: Matriz de imágenes por año (filas) y mes (columnas).
- **Botón de regreso**: Flecha que vuelve a IMAGENES.

## Reglas de negocio
- **Unidad de conteo**: Se suma la columna CANTIDAD (estudios), no se cuentan filas.
- **Año por defecto**: Sin año elegido, el total y el promedio muestran el año cerrado.

## Observaciones
- **Nombre de página**: En Power BI la página se llama ESPECIALIDAD IMAGENES; la documentación del propietario la titula «AREA DE SERVICIO IMAGENES». La correspondencia es probable (por el botón de llegada y el contenido, porque la página del PBIP no trae visuales); por confirmar.
- **Descripción del documento**: Dice que el visual de áreas es un gráfico de barras; la captura muestra un mapa de árbol.
- **Copia en laboratorio**: El documento de LABORATORIO CLÍNICO incluye una sección «IMAGENES POR AREA» con la misma captura de esta página.
- **Mapa de árbol sin año**: En la captura el mapa de árbol coincide con el total del año cerrado; por confirmar si sigue al segmentador de Año.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
