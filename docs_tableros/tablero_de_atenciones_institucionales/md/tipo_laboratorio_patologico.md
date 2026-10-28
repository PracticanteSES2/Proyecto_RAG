---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: TIPO LABORATORIO PATOLOGICO
nombre_funcional: Laboratorios de patología por aseguradora y categoría EPS
bloque: Histórico
tablas: [LABORATORIOS_PATOLOGICOS, Calendario]
actualizado: 2026-10-28
version: 2
---

# TIPO LABORATORIO PATOLOGICO

## Propósito
Muestra cuántos laboratorios de patología corresponden a cada aseguradora y a cada categoría EPS, con el total anual y el promedio mensual. Se llega con el botón ASEGURADOR de la página LABORATORIO PATOLOGICO.

## Fuentes de datos
- **LABORATORIOS_PATOLOGICOS**: La misma tabla de LABORATORIO PATOLOGICO: solicitudes de patología desde 2025-01-01 con aseguradora (nombre del tercero) y categoría EPS.

## Indicadores
- **Laboratorios por aseguradora**: Conteo de laboratorios por Aseguradora. Medida por confirmar (en la página principal es Count de Consecutivo).
- **Laboratorios por categoría EPS**: Conteo y porcentaje del total por CategoriaEPS.
- **Total laboratorios anual**: Igual que en LABORATORIO PATOLOGICO. Por confirmar que use el mismo filtro de fecha de solicitud.
- **Promedio mensual**: Igual que en LABORATORIO PATOLOGICO (Promedio_Laboratorio_pat). Por confirmar.

## Visuales
- **Segmentadores**: ASEGURADORA, Año, Mes y TIPO PATOLOGIA.
- **Mapa de árbol por aseguradora**: «CANTIDAD LABORATORIOS PATOLOGICOS POR ASEGURADOR» con un recuadro por aseguradora proporcional a su cantidad.
- **Tarjetas de laboratorios**: «PROMEDIO MENSUAL» y «TOTAL LABORATORIOS ANUAL».
- **Tabla de conteo**: Matriz de laboratorios por año (filas) y mes (columnas).
- **Gráfico por categoría EPS**: Anillo «TOTAL LABORATORIOS PATOLOGICOS POR CATEGORIA EPS» con CONTRIBUTIVO/SUBSIDIADA, MEDICINA PREPAGADA, PARTICULAR, POLIZA y PLAN COMPLEMENTARIO.
- **Botón de regreso**: Flecha que vuelve a LABORATORIO PATOLOGICO.

## Reglas de negocio
- **Aseguradora sin agrupar**: La aseguradora es el nombre comercial del tercero, sin la agrupación NUEVA EPS / SURA / SANITAS de otras páginas.
- **Categoría EPS**: 125 medicina prepagada, 126 póliza, 127 particular, 122 plan complementario y el resto contributivo/subsidiada.

## Observaciones
- **Nombre de página**: En Power BI la página se llama TIPO LABORATORIO PATOLOGICO; la documentación del propietario la titula «LABORATORIOS PATOLOGICOS». La correspondencia es probable (por el botón de llegada y el contenido, porque la página del PBIP no trae visuales); por confirmar.
- **Nombre parecido**: La página principal se llama LABORATORIO PATOLOGICO; se distinguen por el plural.
- **Mapa y anillo con otro periodo**: En la captura el mapa de árbol y el anillo suman más que el total anual; parecen incluir todos los años. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
