---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: TRIAGES OBSTÉTRICOS
nombre_funcional: Volumen y clasificación de triages obstétricos
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE, Calendario, TERCERO]
actualizado: 2026-10-20
version: 1
---

# TRIAGES OBSTÉTRICOS

## Propósito
Muestra cuántos triages obstétricos se hacen cada mes, compara los años y su distribución por clasificación. Es la entrada al grupo de páginas de obstetricia: desde aquí se llega a OPORTUNIDAD TRIAGE OBSTÉTRICO, CONSULTAS OBSTÉTRICAS, PACIENTES OBSERVADOS OBSTETRICIA, PARTOS y ABORTOS.

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: Triages desde 2023-01-01 hasta hoy con clasificación, asegurador, fecha, hora, día de la semana, grupo de edad y minutos de espera; excluye el código UA. Es la misma tabla de la página TRIAGE general.

## Indicadores
- **Total triages**: Número de triages obstétricos del periodo. Medida de la tarjeta por confirmar; la documentación lista TRIAGES_2024, TRIAGES_2025 y TRIAGES_2026.
- **Triages por año**: Triages de un año fijo. Cálculo: TRIAGES_2025 = CALCULATE(COUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE]), YEAR(OPORTUNIDAD_TRIAGE[FECHA]) = 2025); igual para 2024 y 2026.
- **Promedio mensual triages**: Promedio de triages por mes. Medida por confirmar.

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes y casillas MAYORES DE EDAD / MENORES DE EDAD.
- **Gráfico de triages por mes**: Líneas «TRIAGES POR MES» con el número de triages por mes, una línea por año.
- **Tarjetas de triages**: «TOTAL TRIAGES» y «PROMEDIO MENSUAL TRIAGES».
- **Gráfico por clasificación**: Torta «TRIAGES por CLASIFICACIÓN» con la proporción de cada código obstétrico (I-G, II-G, III-G, IV-G y V-G).
- **Tabla de detalle anual**: Matriz de triages por año (filas) y mes (columnas).
- **Botones de navegación**: OPORTUNIDAD TRIAGE, CONSULTAS URGENCIAS, PACIENTES OBSERVADAS, PARTOS y ABORTOS; el botón de casa vuelve a INICIO.

## Reglas de negocio
- **Triage obstétrico**: Son los códigos con sufijo -G: I-G emergencia obstétrica, II-G urgencia médica obstétrica, III-G urgencia obstétrica, IV-G no urgente obstétrica y V-G consulta externa obstétrica.
- **Grupo de edad**: MENORES DE EDAD si la edad registrada en el triage es menor de 18 años; si no, MAYORES DE EDAD.
- **Agrupación de aseguradoras**: Nombres con NUEVA se agrupan como NUEVA EPS; SURA (sin seguros de vida ni Suramericana) como SURA; SANITAS (sin Colsanitas ni Medisanitas) como SANITAS; MALLAMAS como MALLAMAS; el resto conserva su nombre.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Filtro obstétrico no documentado**: La consulta trae todos los triages; la documentación no dice cómo la página se limita a los códigos -G (la captura solo muestra códigos -G). Por confirmar.
- **Medidas de año fijo**: Las medidas TRIAGES_2024/2025/2026 tienen el año escrito en la fórmula y no siguen al año seleccionado.
- **Total distinto a la torta**: En la captura la tarjeta de total no coincide con la suma de la torta; la tarjeta parece limitarse a un año. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
