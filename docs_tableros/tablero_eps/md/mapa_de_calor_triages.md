---
tablero: TABLERO EPS
pagina: MAPA DE CALOR TRIAGES
nombre_funcional: Triages atendidos por tramo horario y día de la semana
bloque: Histórico
tablas: [OPORTUNIDAD_TRIAGE, Calendario]
actualizado: 2026-10-28
version: 2
---

# MAPA DE CALOR TRIAGES

## Propósito
Matriz de calor con la cantidad de triages atendidos por hora del día y día de la semana, para reconocer los horarios de mayor y menor demanda y planear el personal de urgencias. Es histórica (desde 2022). Se llega con el botón MAPA DE CALOR TRIAGES de la página principal.

## Fuentes de datos
- **Consulta de triages**: Triages de DIM_TRIAGE desde el 2022-01-01 hasta hoy con TramoHorario, DIA_SEMANA y ASEGURADORA; excluye la clasificación UA.

## Indicadores
- **Triages atendidos**: Cantidad de triages en cada combinación de tramo horario y día de la semana. Unidad: triages. DISTINCTCOUNT de OPORTUNIDAD_TRIAGE[OID_TRIAGE] sin los triages obstétricos ni MUERTO.

## Visuales
- **Filtros de segmentación**: Listas de Año, Mes y Día (segmentadores «Fecha Año», «Fecha Mes» y «Fecha Día» de Calendario[Fecha]) y ASEGURADORA.
- **Matriz mapa de calor de triages**: Matriz «DIA SEMANA» con OPORTUNIDAD_TRIAGE[DIA_SEMANA] y [TramoHorario]. Filas TRAMO HORARIO (12:00 a. m. a 11:00 p. m.), columnas de 1. LUNES a 7. DOMINGO y totales por fila y columna; color de verde (pocos triages) a rojo (muchos).
- **Botón VOLVER**: Regresa a la página principal.

## Reglas de negocio
- **Tramo horario**: La hora del triage se trunca a la hora en punto (columna TramoHorario).
- **Orden de días**: DIA_SEMANA va numerado de 1. LUNES a 7. DOMINGO.
- **Exclusión de triage UA**: La clasificación UA no se cuenta.

## Observaciones
- **Coincide con la tarjeta principal**: En la captura el total de la matriz es igual a la tarjeta Triages atendidos de la página principal.
- **Dependencia de configuración regional**: DIA_SEMANA usa DATEPART(DW), que supone domingo como primer día de la semana en SQL Server; si cambia esa configuración los días quedan mal nombrados.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
