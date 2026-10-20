---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: HOSPITALIZACIÓN PARCIAL
nombre_funcional: Atenciones mensuales en hospitalización parcial
bloque: Histórico
tablas: [HOSPITALIZACION_PARCIAL, Calendario, MostrarProyeccion]
actualizado: 2026-10-20
version: 1
---

# HOSPITALIZACIÓN PARCIAL

## Propósito
Muestra cuántas atenciones de hospitalización parcial hay cada mes en los últimos tres años, con proyección opcional, y a qué aseguradoras pertenecen los pacientes.

## Fuentes de datos
- **HOSPITALIZACION_PARCIAL**: Todas las filas de la vista ATC_HOSPI_PARCIAL (estancias en camas de hospitalización parcial con ingreso, cama, fechas de ingreso y egreso, días de estancia, aseguradora, diagnóstico CIE10, CMD y GRD); FECHA es la fecha de ingreso a la cama, sin hora.

## Indicadores
- **Atenciones de hospitalización parcial**: Número de filas (atenciones) del periodo filtrado. Cálculo: ATENCION_HP = COUNTROWS('HOSPITALIZACION_PARCIAL').
- **Atenciones por año**: Atenciones de un año fijo. Cálculo: ATEHP2025 = CALCULATE([ATENCION_HP], Calendario[Año] = 2025); igual para 2024 y 2026.
- **Promedio de atenciones**: Promedio mensual de atenciones. Medida por confirmar (en el modelo PROM_ATENCION_HP usa el año anterior cuando no hay filtro de tiempo).
- **Proyección de atenciones**: Atenciones proyectadas por mes según el crecimiento de los dos años anteriores. Medida por confirmar (en el modelo PROYECCION_ATENHP); solo se ve con «Mostrar proyección» = SI.

## Visuales
- **Segmentadores**: ASEGURADORA, Año, Mes y DIAGNOSTICO.
- **Casilla Mostrar proyección**: Casilla «SI» que muestra u oculta la línea de proyección.
- **Gráfico de atenciones por mes**: Líneas «CANTIDAD MENSUAL DE ATENCIONES HOSPITALIZACION PARCIAL», una línea por año y una línea PROYECCION.
- **Tabla de detalle anual**: Matriz de atenciones por año (filas) y mes (columnas).
- **Tabla de aseguradoras**: Tabla con ASEGURADORA y ATENCIONES (total de pacientes atendidos por aseguradora), ordenada de mayor a menor, con total.
- **Tarjetas de atenciones**: «TOTAL ATENCIONES» y «PROMEDIO ATENCIONES».
- **Botón de inicio**: Botón de casa que vuelve a INICIO.

## Reglas de negocio
- **Unidad de conteo**: Cada fila de la vista cuenta como una atención; un paciente con varias estancias en el periodo cuenta varias veces.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Medidas no documentadas**: La documentación lista solo ATENCION_HP y ATEHP2024/2025/2026; las medidas de promedio y proyección de las tarjetas y del gráfico no aparecen. Por confirmar.
- **Campo del filtro de diagnóstico**: No se documenta qué columna usa el segmentador DIAGNOSTICO (CIE10, CMD o GRD). Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
