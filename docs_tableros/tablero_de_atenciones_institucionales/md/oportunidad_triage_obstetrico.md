---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: OPORTUNIDAD TRIAGE OBSTÉTRICO
nombre_funcional: Tiempo de oportunidad en la clasificación del triage obstétrico
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE, Calendario, TERCERO]
actualizado: 2026-10-28
version: 2
---

# OPORTUNIDAD TRIAGE OBSTÉTRICO

## Propósito
Muestra el tiempo promedio, en minutos, desde la llegada de la paciente hasta su clasificación de triage obstétrico, mes a mes y por año. Se llega desde el botón OPORTUNIDAD TRIAGE de TRIAGES OBSTÉTRICOS y se vuelve con la flecha.

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: Triages desde 2023-01-01 hasta hoy, sin el código UA, con hora de llegada (turno del portero), hora del triage y minutos entre ambas.

## Indicadores
- **Oportunidad de clasificación de triage**: Promedio de minutos entre la llegada (LLEGADA_PORTERO) y la hora del triage (FECHA_TRIAGE). Cálculo: promedio de OPORTUNIDAD_TRIAGE[MIN]; la documentación cita PROMEDIO_TRIAGE_2025 = CALCULATE(AVERAGE(OPORTUNIDAD_TRIAGE[MIN]), YEAR(OPORTUNIDAD_TRIAGE[FECHA]) = 2025). Unidad: minutos.
- **Crecimiento de triages**: Variación frente al mismo periodo del año anterior. Cálculo: Crecimiento_TRIAGES = DIVIDE([TOTAL_TRIAGES] - [Triages_Año_Anterior], [Triages_Año_Anterior]).

## Visuales
- **Segmentadores**: Clasificación Triage, ASEGURADOR, Año, Mes y casillas MAYORES DE EDAD / MENORES DE EDAD.
- **Gráfico de oportunidad**: Líneas «OPORTUNIDAD PARA LA CLASIFICACIÓN DE TRIAGE» con el promedio mensual de minutos, una línea por año.
- **Tabla de detalle anual**: Matriz con el promedio de minutos por año (filas) y mes (columnas).
- **Botón de regreso**: Flecha que vuelve a TRIAGES OBSTÉTRICOS.

## Reglas de negocio
- **Hora de llegada**: Si la paciente no tiene turno de portería (HCCFECTUR), LLEGADA_PORTERO se toma igual a la hora del triage; en ese caso MIN queda vacío y no entra al promedio.
- **Triage obstétrico**: Se analizan los códigos -G (I-G, II-G, III-G, IV-G y V-G).

## Observaciones
- **Nombre de página**: Coincide con la página OPORTUNIDAD TRIAGE OBSTÉTRICO del PBIP.
- **DAX con error**: En la documentación Crecimiento_TRIAGES aparece sin la coma entre los dos argumentos de DIVIDE; en el modelo está bien escrita.
- **Medida del gráfico**: La única medida que lista la documentación para esta página es Crecimiento_TRIAGES, que no corresponde al gráfico de minutos. Medida exacta del gráfico por confirmar.
- **Regla de triage I**: En otra copia de esta consulta (página OPORTUNIDAD DE TRIAGE) los triages I se fijan en 2 minutos; en la consulta de esta página no. Por confirmar cuál está vigente.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
