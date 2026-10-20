---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: URGENCIAS
nombre_funcional: Consultas médicas de urgencias por mes y clasificación
bloque: Histórico
tablas: [CONSULTA_URGENCIAS, Calendario, TERCERO]
actualizado: 2026-10-20
version: 1
---

# URGENCIAS

## Propósito
Muestra cuántas consultas médicas de urgencias se hacen cada mes, compara los años y muestra su distribución por clasificación de triage. Se llega con el botón URGENCIAS de INICIO y desde aquí se abren PACIENTES OBSERVADOS, CONSULTAS PRIORITARIAS, OPORTUNIDAD CONSULTA URGENCIAS y CONSULTAS SIN TRIAGE.

## Fuentes de datos
- **CONSULTA_URGENCIAS**: Ingresos por urgencias con triage, fecha de admisión, primer folio (consulta), clasificación, aseguradora agrupada, plan de beneficio, causa de ingreso, diagnóstico principal, grupo de edad y minutos hasta la consulta. Se une al Calendario por FECHA_ADMISION. Detalle de filtros en OPORTUNIDAD CONSULTA URGENCIAS.

## Indicadores
- **Consultas de urgencias**: Número de consultas del periodo. Medida del modelo Total_consultas_urgencias = COUNT(CONSULTA_URGENCIAS[DOCUMENTO]). Por confirmar que sea la del gráfico.
- **Consultas del año en curso**: Cálculo: PRIORITARIAS_ACT = CALCULATE(DISTINCTCOUNT(CONSULTA_URGENCIAS[DOCUMENTO]), YEAR(CONSULTA_URGENCIAS[FECHA_FOLIO]) = YEAR(TODAY())). La documentación la define con COUNT.
- **Promedio mensual de consultas**: Consultas del año en curso divididas entre el número del mes actual. Medida del modelo PROM_CONSULTAS. Por confirmar que sea la de la tarjeta.
- **Consultas por año**: PRIORITARIAS_2023 cuenta 2023; PRIORITARIAS_2024 y PRIORITARIAS_2025 cuentan en realidad el año en curso (YEAR(TODAY()-1) y YEAR(TODAY())).

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes y Día.
- **Botones de vista**: GENERAL, URGENCIAS y OBSTETRICIA cambian los visuales al grupo de consultas elegido.
- **Botones de grupo de edad**: MAYORES DE EDAD y MENORES DE EDAD.
- **Tarjetas de consultas**: «CONSULTAS MÉDICAS DE URGENCIAS» y «PROMEDIO MENSUAL DE CONSULTAS MÉDICAS DE URGENCIAS».
- **Gráfico de consultas por mes**: Líneas «CONSULTAS MÉDICAS DE URGENCIAS» con el número de consultas por mes, una línea por año.
- **Gráfico por clasificación**: Torta «CONSULTAS por CLASIFICACION» con la proporción de cada código de triage.
- **Tabla de detalle anual**: Matriz de consultas por año (filas) y mes (columnas).
- **Botones de páginas relacionadas**: PACIENTES OBSERVADOS, CONSULTAS PRIORITARIAS, OPORTUNIDAD CONSULTA y CONSULTAS SIN TRIAGE; el botón de casa vuelve a INICIO.

## Reglas de negocio
- **Consulta de urgencias**: Ingreso por urgencias (AINURGCON = 0) con al menos un folio de historia clínica; el primer folio marca la consulta.
- **Grupo de edad**: MENORES si la edad al momento del triage es menor de 18 años (columna MENORES_EDAD_CONS lo muestra como MENORES DE EDAD o MAYORES DE EDAD).
- **Clasificación**: Se agrupa igual que en TRIAGE (IIIU en III; IIP e IIS en II; UA excluido).

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Consulta desactualizada**: La consulta documentada para esta página trae OID_TRIAGE, TIPO_TRIAGE y TIEMPO_PARA_CONSULTA desde 2023; el modelo actual coincide con la consulta de OPORTUNIDAD CONSULTA URGENCIAS, que carga desde 2025-01-01 y no tiene OID_TRIAGE. Por confirmar si la página ya no muestra 2023 y 2024.
- **Medidas con COUNT de OID_TRIAGE**: La documentación cuenta CONSULTA_URGENCIAS[OID_TRIAGE], columna que ya no existe; el modelo cuenta DOCUMENTO.
- **Nombre PRIORITARIAS**: Las medidas de esta página se llaman PRIORITARIAS aunque cuentan todas las consultas de urgencias.
- **Fecha de unión**: La tabla se une al Calendario por fecha de admisión, pero las medidas por año filtran por fecha del folio.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
