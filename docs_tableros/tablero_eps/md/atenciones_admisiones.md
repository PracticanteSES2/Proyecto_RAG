---
tablero: TABLERO EPS
pagina: % ATENCIONES / ADMISIONES
nombre_funcional: Porcentaje de atenciones frente a admisiones por hora y día de la semana
bloque: Histórico
tablas: [ATENCIONES_ADMISIONES, DISPERSION_DIA]
actualizado: 2026-10-20
version: 1
---

# % ATENCIONES / ADMISIONES

## Propósito
Compara las atenciones (triages realizados) con las admisiones o llegadas a urgencias por tramo horario y día de la semana, para ver en qué horas el servicio responde menos a la demanda. Es histórica (desde 2022), con una tabla adicional del día en curso. Se llega con el botón %ATENCIONES de la página principal.

## Fuentes de datos
- **Consulta de triages**: Triages desde el 2022-01-01 con tramo horario y día de la semana; excluye la clasificación UA.
- **Consulta de llegadas y atendidos del día**: Por cada hora de hoy, triages realizados (HCNTRIAGE), llegadas (ADMISIONTRIAGE) y pendientes; se recalcula con cada actualización.

## Indicadores
- **Porcentaje de atenciones por tramo**: Relación entre atenciones y admisiones en cada hora y día de la semana. Unidad: porcentaje. Fórmula por confirmar.
- **Porcentaje de atendidos del día**: Atendidos sobre llegadas en cada hora de hoy (columna %ATENDIDOS). Unidad: porcentaje. Fórmula exacta por confirmar.
- **Pendientes por tramo**: Llegadas menos atendidos en la hora (PENDIENTES_TRAMO). Unidad: pacientes.
- **Pendientes acumulados**: Suma acumulada de pendientes desde el inicio del día; si es negativa se muestra 0 (PENDIENTES_ACUMULADOS). Unidad: pacientes.

## Visuales
- **Filtros de segmentación**: Listas de Año, Mes, Día y ASEGURADORA.
- **Matriz de porcentaje de atenciones**: Filas por tramo horario (12:00 a. m. a 11:00 p. m.) y columnas por día de la semana (1. LUNES a 7. DOMINGO) con totales; escala de color de rojo (porcentaje bajo) a verde (alto).
- **Tabla atención día actual**: Titulada «ATENCIÓN DÍA ACTUAL»; columnas TRAMO y %ATENDIDOS de cada hora de hoy, con total y color verde para valores altos.
- **Control de reproducción por mes**: Botones de reproducir, pausar, detener y avanzar que recorren los meses y animan la matriz.
- **Botones de navegación**: VOLVER regresa a la página principal; GRÁFICO DE DISPERSIÓN lleva a DISPERSIÓN GENERAL.

## Reglas de negocio
- **Tramo horario**: La hora del triage y de la llegada se trunca a la hora en punto para agrupar.
- **Llegadas y atendidos del día**: Solo cuentan registros con fecha de hoy; las horas sin llegadas o sin atenciones se completan con 0.
- **Piso de pendientes acumulados**: El acumulado de pendientes nunca se muestra negativo; si da menos de 0 se muestra 0.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Fórmula del porcentaje sin documentar**: La documentación no trae la medida de la matriz; los valores de la captura (entre 20 % y 33 %, total general 107,48 %) no permiten deducirla. Por confirmar.
- **Valor «Infinito»**: En la tabla del día aparece «Infinito» en horas sin llegadas y valores mayores a 100 % cuando se atienden pacientes que llegaron en horas anteriores; la división no protege el denominador cero.
- **Piso solo en la salida**: El acumulado se corta en 0 solo al mostrarlo; la suma interna sigue negativa y puede ocultar pendientes de horas posteriores.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
