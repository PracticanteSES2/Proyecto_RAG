---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: ESPECIALIDADES CIRUGIA
nombre_funcional: Cirugías realizadas por especialidad
bloque: Histórico
tablas: [CIRUGIAS, Calendario]
actualizado: 2026-10-28
version: 2
---

# ESPECIALIDADES CIRUGIA

## Propósito
Muestra cómo se distribuyen las cirugías realizadas entre las especialidades médicas, para ver cuáles concentran más procedimientos. Incluye el tiempo de oportunidad de la cirugía ambulatoria. Se llega desde el botón DETALLE ESPECIALIDADES de la página CIRUGÍAS.

## Fuentes de datos
- **CIRUGIAS**: Cirugías realizadas (vista CIRUGIAS_DWSES) con especialidad, aseguradora y fecha de cirugía; sin filtro de fechas en la consulta.

## Indicadores
- **Cirugías realizadas**: Número de cirugías del periodo filtrado; mismo cálculo que en la página CIRUGÍAS.
- **Promedio mensual de cirugías**: Cálculo PROM_CIRUGÍAS = COUNT(CIRUGIAS[INGRESO])/MONTH(TODAY()).
- **Oportunidad de cirugía ambulatoria**: Promedio de días en que se presta la cirugía ambulatoria. Medida por confirmar.

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes y ESPECIALIDAD.
- **Tarjetas de cirugías**: «CIRUGÍAS REALIZADAS» y «PROMEDIO MENSUAL».
- **Mapa de árbol por especialidad**: Treemap «CIRUGÍAS REALIZADAS POR ESPECIALIDAD» con el número de cirugías de cada especialidad (por ejemplo ginecología-obstetricia, cirugía general, ortopedia).
- **Medidor de oportunidad**: Medidor «OPORTUNIDAD DE CIRUGÍA AMBULATORIA (DÍAS)» con el promedio de días.
- **Botón de inicio**: Botón de casa que vuelve a INDICADORES.

## Reglas de negocio
- **Especialidad**: Se usa la especialidad registrada en la cirugía (CIRUGIAS[ESPECIALIDAD]), sin agrupaciones adicionales.

## Observaciones
- **Nombre de página**: En Power BI la página se llama ESPECIALIDADES CIRUGIA; la documentación del propietario la titula «CIRUGÍAS ESPECIALIDADES».
- **Medida de oportunidad no documentada**: La documentación no indica la medida del medidor de oportunidad. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
