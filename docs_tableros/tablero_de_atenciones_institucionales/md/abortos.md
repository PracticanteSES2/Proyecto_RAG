---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: ABORTOS
nombre_funcional: Abortos e IVE registrados por mes
bloque: Histórico
tablas: [PARTOS_DRIVE, Calendario]
actualizado: 2026-10-20
version: 1
---

# ABORTOS

## Propósito
Muestra cuántos abortos se registran cada mes en los últimos tres años, separando la interrupción voluntaria del embarazo (IVE) del aborto no seguro. Se llega desde el botón ABORTOS de TRIAGES OBSTÉTRICOS y se vuelve con la flecha.

## Fuentes de datos
- **PARTOS_DRIVE**: El mismo archivo Excel de gestantes (partos MSPS) de epidemiología que usa la página PARTOS; los abortos son las filas cuyo tipo es ABORTO o IVE. Tabla del modelo por confirmar.

## Indicadores
- **Total abortos**: Número de abortos del periodo. Medida por confirmar.
- **Promedio mensual de abortos**: Promedio de abortos por mes. Medida por confirmar.

## Visuales
- **Selector tipo de aborto**: Botones «TIPO DE PARTO» con las opciones ABORTO e IVE que filtran la página.
- **Gráfico de abortos**: Líneas «ABORTOS» con el conteo (recuento de Documento) por mes, una línea por año.
- **Tabla de conteo de abortos**: Matriz de abortos por año (filas) y mes (columnas).
- **Tarjetas de abortos**: «TOTAL ABORTOS» y «PROMEDIO MENSUAL ABORTOS».
- **Botón de regreso**: Flecha que vuelve a TRIAGES OBSTÉTRICOS.

## Reglas de negocio
- **Tipos de aborto**: IVE es interrupción voluntaria del embarazo; ABORTO corresponde al aborto no seguro.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Medidas no documentadas**: La documentación no lista medidas para esta página.
- **Visuales rotos**: En la captura tres visuales de la parte superior muestran «Corregir esto» (error de campo). Por confirmar cuáles son.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
