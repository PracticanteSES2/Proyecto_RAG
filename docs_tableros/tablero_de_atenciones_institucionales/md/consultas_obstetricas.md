---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: CONSULTAS OBSTÉTRICAS
nombre_funcional: Volumen de consultas obstétricas prioritarias
bloque: Histórico
tablas: [CONSULTA_URGENCIAS, Calendario, TERCERO]
actualizado: 2026-10-20
version: 1
---

# CONSULTAS OBSTÉTRICAS

## Propósito
Muestra cuántas consultas obstétricas prioritarias de urgencias se atienden cada mes y su distribución por clasificación de triage. Se llega desde el botón CONSULTAS URGENCIAS de TRIAGES OBSTÉTRICOS; sus botones ATENCIONES y OPORTUNIDAD CONSULTA cambian entre esta página y OPORTUNIDAD CONSULTA OBSTÉTRICA.

## Fuentes de datos
- **CONSULTA_URGENCIAS**: Triages desde 2023-01-01 hasta hoy (sin el código UA) con su ingreso, hora de admisión y primer folio de historia clínica; excluye ingresos en estado 2 o 4. Trae clasificación, asegurador, grupo de edad y minutos hasta la consulta.

## Indicadores
- **Consultas prioritarias año actual**: Consultas cuyo primer folio es del año en curso. Cálculo: PRIORITARIAS_2025 = CALCULATE(COUNT(CONSULTA_URGENCIAS[DOCUMENTO]), YEAR(CONSULTA_URGENCIAS[FECHA_FOLIO]) = YEAR(TODAY())).
- **Promedio mensual de consultas prioritarias**: Consultas del año en curso divididas por el número del mes actual. Medida por confirmar (en el modelo existe PROM_CONSULTAS con ese cálculo).
- **Consultas año anterior**: Medida PRIORITARIAS_2024 = CALCULATE(COUNT(CONSULTA_URGENCIAS[DOCUMENTO]), YEAR(CONSULTA_URGENCIAS[FECHA_FOLIO]) = YEAR(TODAY()-1)).

## Visuales
- **Segmentadores**: EPS, Año, Mes y casillas MAYORES DE EDAD / MENORES DE EDAD.
- **Gráfico de consultas prioritarias**: Líneas «CONSULTAS PRIORITARIAS» con el número de consultas por mes, una línea por año.
- **Tarjetas de consultas**: «CONSULTAS PRIORITARIAS AÑO ACTUAL» y «PROMEDIO MENSUAL DE CONSULTAS PRIORITARIAS».
- **Gráfico por clasificación**: Torta «CONSULTAS por CLASIFICACIÓN TRIAGE» con la proporción de códigos I-G, II-G, III-G y IV-G.
- **Tabla de detalle anual**: Matriz de consultas por año (filas) y mes (columnas).
- **Botones de navegación**: ATENCIONES (esta página) y OPORTUNIDAD CONSULTA; el botón de casa vuelve a INICIO.

## Reglas de negocio
- **Tiempo para consulta**: Minutos desde el triage hasta el primer folio; desde el 2025-08-01, para triage II se mide hasta la admisión.
- **Grupo de edad**: MENORES si la edad al momento del triage es menor de 18 años; si no, MAYORES.
- **Agrupación de aseguradoras**: NUEVA EPS, SURA (sin ARL, seguros de vida ni Suramericana), SANITAS (sin Colsanitas ni Medisanitas) y MALLAMAS se agrupan por nombre; el resto conserva su nombre.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Año anterior mal calculado**: PRIORITARIAS_2024 usa YEAR(TODAY()-1), que es el año de ayer (el año en curso) y no el año anterior.
- **Nombres de medidas**: PRIORITARIAS_2025 y PRIORITARIAS_2024 se calculan con el año actual, no con 2025 ni 2024.
- **Columna contada**: La documentación cuenta CONSULTA_URGENCIAS[OID_TRIAGE], que no existe en el modelo; el modelo cuenta DOCUMENTO.
- **Consulta desactualizada**: El modelo tiene columnas que la consulta documentada no produce (IDENTIFICACION, INGRESO, DIACODIGO, TIEMPO_CONSULTA_CALCULADA) y no tiene TIEMPO_PARA_CONSULTA. Por confirmar la consulta vigente.
- **Filtro obstétrico no documentado**: La torta solo muestra códigos -G; la documentación no dice dónde se aplica ese filtro. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
