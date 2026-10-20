---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: CIRUGÍAS
nombre_funcional: Volumen mensual de cirugías realizadas y oportunidad quirúrgica
bloque: Histórico
tablas: [CIRUGIAS, OPORTUNIDAD CIRUGIA, Calendario, MostrarProyeccion]
actualizado: 2026-10-20
version: 1
---

# CIRUGÍAS

## Propósito
Muestra cuántas cirugías se realizan cada mes, compara los años y permite ver una proyección del año. Incluye el tiempo de oportunidad de la cirugía ambulatoria en días. Desde esta página se llega a CANCELACIONES, PENDIENTES y al detalle por especialidad (CIRUGÍAS ESPECIALIDADES).

## Fuentes de datos
- **CIRUGIAS**: Cirugías realizadas (vista CIRUGIAS_DWSES) con su ingreso, aseguradora y EPS; FECHA es la fecha de la cirugía sin hora. La consulta no tiene filtro de fechas (el filtro está comentado).
- **OPORTUNIDAD CIRUGIA**: Solicitudes de cirugía programada (TipoCirugiaOid = 1) planeadas desde 2025-01-01, con la primera fecha en que pasaron por cada estado quirúrgico. Por confirmar que es la fuente del indicador de oportunidad.

## Indicadores
- **Cirugías realizadas**: Número de cirugías del periodo filtrado. Cálculo: TOTAL_CIRUGIAS = COUNT(CIRUGIAS[CEDULA]) (medida tomada del modelo; por confirmar que es la de la tarjeta).
- **Promedio mensual de cirugías**: Cirugías divididas por el número del mes actual. Cálculo: PROM_CIRUGÍAS = COUNT(CIRUGIAS[INGRESO])/MONTH(TODAY()).
- **Cirugías año actual**: Cirugías del año en curso. Cálculo: Cirugias_Año_Actual = CALCULATE([TOTAL_CIRUGIAS], Calendario[Año]=YEAR(TODAY())).
- **Cirugías año anterior**: Cirugías del año anterior según la fecha de cirugía. Cálculo: CALCULATE(COUNT(CIRUGIAS[CUPS]), YEAR(CIRUGIAS[FECHA_CIRUGIA]) = YEAR(TODAY())-1).
- **Proyección de cirugías**: Para cada mes, cirugías del mismo mes del año anterior multiplicadas por (1 + crecimiento entre ese mes del año anterior y el de hace dos años). Medida PROYECCION_CIRUGIAS; solo se muestra si «Mostrar proyección» = SI.
- **Oportunidad de cirugía ambulatoria**: Promedio de días de oportunidad de la cirugía ambulatoria. Medida por confirmar (posiblemente la columna OPORTUNIDAD de OPORTUNIDAD CIRUGIA, días entre Planeada y Paciente En Salida).

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes, ESPECIALIDAD y TIPO INGRESO en la parte superior, más un segmentador TIPO que filtra la cirugía según su tipo de origen.
- **Casilla Mostrar proyección**: Casilla «SI» que muestra u oculta la línea de proyección del gráfico.
- **Gráfico de cirugías realizadas**: Líneas «CIRUGÍAS REALIZADAS» con la cantidad de cirugías por mes; una línea por año y una línea PROYECCIÓN.
- **Medidor de oportunidad**: Medidor «OPORTUNIDAD DE CIRUGÍA AMBULATORIA (DÍAS)» con el promedio de días de oportunidad.
- **Tabla de detalle anual**: Matriz de cirugías por año (filas) y mes (columnas).
- **Tarjetas de cirugías**: «CIRUGÍAS REALIZADAS» (total del periodo) y «PROMEDIO MENSUAL».
- **Botones de navegación**: CANCELACIONES, PENDIENTES y DETALLE ESPECIALIDADES; el botón de casa vuelve a INICIO.

## Reglas de negocio
- **Base de la proyección**: La proyección necesita datos del mismo mes en los dos años anteriores al año seleccionado; si falta alguno o el de hace dos años es 0, no se calcula.
- **Estados quirúrgicos**: La fecha de cada estado es la primera vez que la solicitud pasó por él: 1 Planeada, 36 Consulta externa, 18 Por autorizar, 24 Documentación entregada por facturación, 6 No autorizado, 23 Espera preanestésico, 19 Espera programación, 5 Trámite clínico/ADM, 7 Programado, 9 Sala de espera, 10 Quirófano, 11 Recuperación, 13 Salida y 8 Cancelado.
- **Médico de la solicitud**: Si el médico registrado es el código genérico 5000, se usa el nombre del médico que solicita.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Proyección sin año seleccionado**: PROYECCION_CIRUGIAS toma el año con SELECTEDVALUE; si no hay un único año seleccionado el año queda vacío y la proyección no aparece. Por confirmar si es intencional.
- **Promedio mensual entre años**: PROM_CIRUGÍAS divide por el mes actual el conteo de todos los años filtrados; sin filtro de año mezcla varios años.
- **DAX con texto dañado**: En la documentación el DAX de PROYECCION_CIRUGIAS aparece con el nombre partido («_CIRUGIAS =», «Capturam PROYECCION os»); el del modelo está completo.
- **Medida de oportunidad no documentada**: La documentación no indica la medida del medidor de oportunidad ni de qué tabla sale. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
