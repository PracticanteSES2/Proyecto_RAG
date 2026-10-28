---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: OPORTUNIDAD CONSULTA OBSTÉTRICA
nombre_funcional: Tiempo de oportunidad de la consulta obstétrica prioritaria
bloque: Histórico
tablas: [CONSULTA_URGENCIAS, Calendario, TERCERO]
actualizado: 2026-10-20
version: 1
---

# OPORTUNIDAD CONSULTA OBSTÉTRICA

## Propósito
Muestra el tiempo promedio de espera, en minutos, para la consulta obstétrica prioritaria de urgencias, mes a mes y por año. Se llega desde el botón OPORTUNIDAD CONSULTA de CONSULTAS OBSTÉTRICAS y se vuelve con la flecha.

## Fuentes de datos
- **CONSULTA_URGENCIAS**: Triages con su ingreso y primer folio de historia clínica; es la tabla de la página CONSULTAS OBSTÉTRICAS. Por confirmar, porque la documentación de esta página trae otra consulta.

## Indicadores
- **Tiempo de oportunidad consulta prioritaria**: Promedio mensual de minutos de espera para la consulta. Unidad: minutos. Medida por confirmar (en el modelo, TIEMPO_OPORTUNIDAD_PRIORITARIAS_ACT = CALCULATE(AVERAGE(CONSULTA_URGENCIAS[tiempo_consulta]), YEAR(CONSULTA_URGENCIAS[FECHA_FOLIO]) = YEAR(TODAY())), con tiempo_consulta en minutos entre admisión y primer folio).
- **Oportunidad año actual**: Tiempo promedio de oportunidad del año en curso. Medida por confirmar.

## Visuales
- **Segmentadores**: Clasificación Triage, ASEGURADOR, Año, Mes y casillas MAYORES DE EDAD / MENORES DE EDAD.
- **Gráfico de oportunidad**: Líneas «TIEMPO OPORTUNIDAD CONSULTA PRIORITARIA» con el promedio mensual de minutos, una línea por año.
- **Tarjeta oportunidad año actual**: Tarjeta «OPORTUNIDAD AÑO ACTUAL».
- **Tabla de detalle anual**: Matriz con el tiempo de oportunidad por año (filas) y mes (columnas).
- **Botón de regreso**: Flecha que vuelve a CONSULTAS OBSTÉTRICAS.

## Reglas de negocio
- **Tiempo para consulta**: Según la consulta de CONSULTAS OBSTÉTRICAS, minutos desde el triage hasta el primer folio; desde el 2025-08-01, para triage II hasta la admisión. Por confirmar cuál de los dos tiempos usa esta página.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Consulta que no corresponde**: La consulta documentada para esta página es la de pacientes observados (tabla OBSERVADOS) y no calcula tiempos de consulta.
- **Capturas que no corresponden**: La captura general y la de la tabla de detalle muestran la página de pacientes observados, no esta página.
- **Tarjeta vacía**: En la captura la tarjeta «OPORTUNIDAD AÑO ACTUAL» muestra «(En blanco)». Por confirmar si la medida tiene datos para el año en curso.
- **Medidas no documentadas**: La documentación no lista medidas para esta página.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
