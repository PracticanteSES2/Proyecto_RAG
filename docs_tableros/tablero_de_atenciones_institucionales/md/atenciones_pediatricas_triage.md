---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: ATENCIONES PEDIÁTRICAS TRIAGE
nombre_funcional: Triages pediátricos por mes y clasificación
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE, Calendario]
actualizado: 2026-10-20
version: 1
---

# ATENCIONES PEDIÁTRICAS TRIAGE

## Propósito
Muestra cuántos triages pediátricos se registran cada mes, compara los años y muestra su distribución por clasificación. Desde qué botón se llega: por confirmar (tiene flecha de regreso).

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: La misma tabla de la página TRIAGE: triages desde 2023-01-01, sin el código UA, con la columna MENORES (grupo de edad según la edad registrada en el triage).

## Indicadores
- **Triages pediátricos de 2025**: Cálculo: TRIAGES_PEDIATRICOS_2025 = CALCULATE(COUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE]), YEAR(OPORTUNIDAD_TRIAGE[FECHA]) = 2025, OPORTUNIDAD_TRIAGE[MENORES] = "MENORES DE EDAD").
- **Tiempo de triage pediátrico 2025**: Cálculo: PROMEDIO_TRIAGES_PEDIATRICOS_2025 = CALCULATE(AVERAGE(OPORTUNIDAD_TRIAGE[TIEMPO_TRIAGE_PROM]), YEAR(OPORTUNIDAD_TRIAGE[FECHA]) = 2025, OPORTUNIDAD_TRIAGE[MENORES] = "MENORES DE EDAD"); en minutos.
- **Promedio mensual de triages**: Medida por confirmar; el modelo tiene PROM_TRIAGE_PEDIATRICOS (triages de menores del año en curso divididos entre el número del mes actual).
- **Triages por mes**: Número de triages por mes. Medida por confirmar (la documentación lista las mismas medidas de la página TRIAGE).

## Visuales
- **Segmentadores**: ASEGURADOR, Año y Mes.
- **Botones de vista**: GENERAL, URGENCIAS y OBSTETRICIA cambian los visuales al grupo de triages elegido.
- **Tarjetas de triages**: «TRIAGES 2025» y «PROMEDIO MENSUAL TRIAGES».
- **Gráfico de triages por mes**: Líneas «TRIAGES POR MES», una línea por año.
- **Gráfico por clasificación**: Torta «TRIAGES PEDIATRICOS por CLASIFICACIÓN» con la proporción de cada código de triage.
- **Tabla de detalle anual**: Matriz de triages por año (filas) y mes (columnas).
- **Botón de regreso**: Flecha que vuelve a la página anterior.

## Reglas de negocio
- **Triage pediátrico**: Triage de un paciente con edad registrada menor de 18 años (MENORES = MENORES DE EDAD).
- **Clasificación**: Se agrupa igual que en TRIAGE (IIIU en III; IIP e IIS en II; UA excluido).

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Tarjeta con año fijo**: La tarjeta «TRIAGES 2025» tiene el año en la fórmula y no cambia con el segmentador.
- **Valores que no cuadran**: En la captura el promedio mensual (190) no corresponde al total de 2025 entre 12 ni a los valores mensuales del gráfico (entre 480 y 970), y la torta suma varios años. Por confirmar si gráfico y torta filtran menores de edad.
- **Medidas copiadas**: La documentación repite todas las medidas de la página TRIAGE, incluida la proyección, aunque esta página no tiene casilla de proyección.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
