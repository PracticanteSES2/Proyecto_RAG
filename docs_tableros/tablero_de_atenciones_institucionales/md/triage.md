---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: TRIAGE
nombre_funcional: Volumen mensual de triages y su clasificación
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE, Calendario, TERCERO, MostrarProyeccion]
actualizado: 2026-10-20
version: 1
---

# TRIAGE

## Propósito
Muestra cuántos triages se hacen cada mes, compara los años, proyecta el año en curso y muestra la distribución por clasificación. Se llega con el botón TRIAGES de INICIO y desde aquí se abre OPORTUNIDAD TRIAGE.

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: Triages desde 2023-01-01 hasta hoy con clasificación, asegurador, hora de llegada, fecha y hora del triage, tramo horario, día de la semana, minutos de espera (MIN) y grupo de edad; excluye el código UA. Se une al Calendario por FECHA y a TERCERO por el asegurador.

## Indicadores
- **Total de triages**: Triages distintos del periodo. Cálculo: TOTAL_TRIAGES = DISTINCTCOUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE]).
- **Triages por año fijo**: Triages de un año escrito en la fórmula. Cálculo: TRIAGES_2025 = CALCULATE(COUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE]), YEAR(OPORTUNIDAD_TRIAGE[FECHA]) = 2025); igual para 2023, 2024 y 2026.
- **Triages del año anterior**: Cálculo: Triages_Año_Anterior = CALCULATE([TOTAL_TRIAGES], SAMEPERIODLASTYEAR(Calendario[Date])).
- **Crecimiento de triages**: Variación frente al mismo periodo del año anterior. Cálculo: Crecimiento_TRIAGES = DIVIDE([TOTAL_TRIAGES] - [Triages_Año_Anterior], [Triages_Año_Anterior]).
- **Proyección mensual de triages**: Medida Proyeccion_Mensual_Visible: triages del mismo mes del año anterior × (1 + crecimiento de ese mes entre los dos años anteriores); solo con «Mostrar proyección» = SI.
- **Tarjetas de triages**: Total anual, promedio mensual y promedio diario de triages. Medidas por confirmar; el modelo tiene Total_Triages_Dinamico, Promedio_Triages_Dinamico y Promedio_Triages_Diario_Dinamico, que usan el año elegido o, sin año elegido, el año cerrado.

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes y Día.
- **Casilla Mostrar proyección**: Casilla «MOSTRAR PROYECCIÓN» que agrega la línea Proyección al gráfico.
- **Botones de vista**: GENERAL, URGENCIAS y OBSTETRICIA cambian los gráficos y la tabla al grupo de triages elegido.
- **Botones de grupo de edad**: MAYORES DE EDAD y MENORES DE EDAD.
- **Tarjetas de triages**: «TRIAGES ANUALES», «PROMEDIO MENSUAL TRIAGES» y «PROMEDIO TRIAGES DIARIOS».
- **Gráfico de triages por mes**: Líneas «TRIAGES POR MES», una línea por año y una de proyección.
- **Gráfico por clasificación**: Torta «TRIAGES por CLASIFICACION» con la proporción de cada código de triage.
- **Tabla de detalle anual**: Matriz de triages por año (filas) y mes (columnas).
- **Botón Oportunidad Triage**: Abre la página OPORTUNIDAD TRIAGE; el botón de casa vuelve a INICIO.

## Reglas de negocio
- **Clasificación**: CLASIFICACION_TRIAGE agrupa IIIU en III e IIP e IIS en II; los códigos -G son obstétricos y UA no se carga.
- **Grupo de edad**: MENORES DE EDAD si la edad registrada en el triage (HCTEDAD) es menor de 18 años.
- **Tramo horario**: La hora del triage se redondea hacia abajo a la hora en punto.
- **Vista obstetricia**: Muestra solo los códigos -G; la vista urgencias los demás. Regla exacta de los botones por confirmar.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Conteo distinto entre medidas**: TOTAL_TRIAGES cuenta triages distintos y TRIAGES_20xx cuenta filas; pueden diferir si un triage se repite.
- **Proyección distinta al modelo**: La documentación toma el año con MAX(Calendario[Año]); el modelo usa el año elegido o, si no hay, el año en curso. Los comentarios de la fórmula hablan de «cirugías» porque se copió de esa página.
- **Torta con otro periodo**: En la captura la torta suma varios años mientras las tarjetas muestran solo el año en curso. Por confirmar.
- **Medidas sin uso claro**: La documentación lista PROMEDIO_TRIAGE_20xx y medidas pediátricas que no corresponden a ningún visual de esta página.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
