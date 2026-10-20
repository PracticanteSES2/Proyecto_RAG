---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: ATENCIÓN DOMICILIARIA
nombre_funcional: Atenciones domiciliarias (SES en tu Hogar) por mes y aseguradora
bloque: Histórico
tablas: [ATENCION DOMICILIARIA, Calendario, MostrarProyeccion]
actualizado: 2026-10-20
version: 1
---

# ATENCIÓN DOMICILIARIA

## Propósito
Muestra cuántas atenciones domiciliarias (programa SES en tu Hogar) hay cada mes, compara los años con proyección opcional y muestra su distribución por aseguradora. Se llega, según parece, con el botón SES EN TU HOGAR de INICIO (por confirmar).

## Fuentes de datos
- **ATENCION DOMICILIARIA**: Todas las filas de la vista ATC_DOMICILIARIA (estancias en camas de hospitalización en casa con ingreso, cama, servicio, fechas de ingreso y egreso de cama, días de estancia, aseguradora, plan, diagnóstico CIE10, CMD, GRD y municipio), más FECHA = fecha de egreso final sin hora. Se une al Calendario por FECHA.

## Indicadores
- **Atenciones domiciliarias**: Número de filas del periodo. Cálculo: ATENCION_DM = COUNTROWS('ATENCION DOMICILIARIA').
- **Atenciones por año fijo**: Cálculo: ATEN_DOM2025 = CALCULATE([ATENCION_DM], Calendario[Año] = 2025); igual para 2024 y 2026.
- **Promedio de atenciones**: Atenciones del año divididas entre 12; sin filtros de tiempo usa el año cerrado y con varios años suma los promedios de cada año. Medida PROM_ATENCION_AD.
- **Proyección de atenciones**: Medida PROYECCION_ATD: para cada mes, atenciones del año anterior × (1 + crecimiento frente al año previo); solo con «Mostrar proyección» = SI.

## Visuales
- **Segmentadores**: ASEGURADORA, Año, Mes y DIAGNOSTICO.
- **Casilla Mostrar proyección**: «MOSTRAR PROYECCIÓN» con la opción SI.
- **Gráfico de atenciones por mes**: Líneas «CANTIDAD MENSUAL DE ATENCION DOMICILIARIA», una línea por año y una de proyección (PROYECCION_ATD).
- **Tabla de aseguradoras**: Tabla ASEGURADORA y ATENCIONES ordenada de mayor a menor, con total.
- **Tabla de detalle anual**: Matriz de atenciones por año (filas) y mes (columnas), con totales.
- **Tarjetas de atenciones**: «ATENCIONES» y «PROMEDIO ATENCIONES», cada una con una pequeña línea de tendencia.
- **Botón de inicio**: Botón de casa que vuelve a INICIO.

## Reglas de negocio
- **Unidad de conteo**: Cada fila de la vista cuenta como una atención; un paciente con varias estancias cuenta varias veces.
- **Fecha de la atención**: La atención se ubica en el mes de su egreso final.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Documento mal titulado**: El documento «SES en tu Hogar» se titula HOSPITALIZACIÓN PARCIAL y sus capturas son de esa página, pero su consulta y medidas son de atención domiciliaria; aquí se tomó como fuente de esta página.
- **Proyección siempre 2025 frente a 2024**: PROYECCION_ATD usa las medidas de año fijo ATEN_DOM2025 y ATEN_DOM2024, así que compara esos años sin importar el año elegido.
- **Dos versiones de la proyección**: El documento de atención domiciliaria trae una versión anterior basada en MAX(Calendario[Año]); el modelo usa la del documento «SES en tu Hogar».
- **Tarjeta ATENCIONES**: En la captura suma todos los años mientras el promedio usa solo el año cerrado. Por confirmar.
- **Campo del filtro de diagnóstico**: No se documenta qué columna usa DIAGNOSTICO (CIE10, CMD o GRD). Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
