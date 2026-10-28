---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: OPORTUNIDAD TRIAGE
nombre_funcional: Tiempo de espera para la clasificación de triage
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE, Calendario, TERCERO]
actualizado: 2026-10-28
version: 2
---

# OPORTUNIDAD TRIAGE

## Propósito
Muestra el tiempo promedio, en minutos, entre la llegada del paciente y su clasificación de triage, mes a mes y comparando años. Se llega con el botón OPORTUNIDAD TRIAGE de la página TRIAGE.

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: La misma tabla de la página TRIAGE: triages desde 2023-01-01 hasta hoy, sin el código UA, con la columna MIN de minutos de espera.

## Indicadores
- **Oportunidad del triage**: Minutos entre el registro de llegada (HCCFECTUR) y la hora del triage (HCTFECTRI). Columna OPORTUNIDAD_TRIAGE[MIN]; el gráfico muestra su promedio por mes (medida del gráfico por confirmar).
- **Promedio de triage por año fijo**: Cálculo: PROMEDIO_TRIAGE_2025 = CALCULATE(AVERAGE(OPORTUNIDAD_TRIAGE[MIN]), YEAR(OPORTUNIDAD_TRIAGE[FECHA]) = 2025); igual para 2026.
- **Tiempo de triage calculado**: Columna TIEMPO_TRIAGE_PROM = DATEDIFF(OPORTUNIDAD_TRIAGE[LLEGADA_PORTERO], OPORTUNIDAD_TRIAGE[FECHA_TRIAGE], MINUTE); la usan las medidas pediátricas.

## Visuales
- **Segmentadores**: Clasificación Triage, ASEGURADOR, Año y Mes.
- **Botones de vista**: GENERAL, URGENCIAS y OBSTETRICIA cambian el gráfico y la tabla al grupo de triages elegido.
- **Botones de grupo de edad**: MAYORES DE EDAD y MENORES DE EDAD.
- **Gráfico de oportunidad**: Líneas «OPORTUNIDAD PARA LA CLASIFICACIÓN DE TRIAGE» con el promedio de minutos por mes, una línea por año; eje de 0 a 60 minutos.
- **Tabla de detalle anual**: Matriz del promedio de minutos por año (filas) y mes (columnas).
- **Botón de regreso**: Flecha que vuelve a TRIAGE.

## Reglas de negocio
- **Triage I**: Los triages de código I se registran con 2 minutos fijos de espera.
- **Sin registro de llegada**: Si no hay hora de llegada, MIN queda vacío y el triage no entra en el promedio.
- **Clasificación**: Se agrupa igual que en TRIAGE (IIIU en III; IIP e IIS en II; UA excluido).

## Observaciones
- **Nombre de página**: Coincide con la página OPORTUNIDAD TRIAGE del PBIP; la documentación del propietario la llama OPORTUNIDAD DE TRIAGE.
- **Dos documentos**: La página está documentada en «Tablero Triage» y en «Oportunidad Triage»; solo el segundo, más reciente, trae la regla de 2 minutos para triage I. Por confirmar cuál está vigente.
- **Promedio 2024 del modelo**: En el modelo PROMEDIO_TRIAGE_2024 filtra el año 2025, aunque la documentación dice 2024.
- **Sin meta**: La documentación no define meta ni semáforo para este tiempo. Por confirmar.
- **Etiqueta sin formato**: En una captura el valor de febrero de 2026 aparece con muchos decimales (5,469387755102041).

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
