---
tablero: DEMANDA INSATISFECHA
pagina: TRIAGES
nombre_funcional: Triages no atendidos
bloque: Histórico
tablas: [TRIAGE]
actualizado: 2026-10-20
version: 1
---

# TRIAGES

## Propósito
Analiza los triages no atendidos: turnos de triage registrados en urgencias que nunca tuvieron triage realizado. Muestra el total, el promedio mensual, la tendencia por mes y los aseguradores con más casos. Es de análisis histórico; se llega desde el botón TRIAGES de CONSOLIDADO. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **TRIAGE**: Turnos de triage (HCNCONTRDT) desde el 1 de enero de 2025 hasta hoy, con clasificación HCNCONCOTRI de 1 a 7 y sin registro en HCNTRIAGE. Trae turno, fecha del turno (HCCFECTUR), estado, asegurador (TERNOMCOM) y la fecha sin hora (FECHA).

## Indicadores
- **Triages no atendidos**: Número de turnos de triage sin triage realizado. DAX: DISTINCTCOUNT(TRIAGE[OID]).
- **Promedio mensual**: Triages no atendidos del año en curso divididos por el número del mes actual. Medida PROM_TRIAGE: DIVIDE(CALCULATE(DISTINCTCOUNT(TRIAGE[OID]), YEAR(TRIAGE[HCCFECTUR]) = YEAR(TODAY())), MONTH(TODAY())).

## Visuales
- **Tarjetas**: TRIAGES NO ATENDIDOS y PROMEDIO MENSUAL.
- **Gráfico de líneas por mes**: Titulado «TRIAGES NO REALIZADOS por Mes»; cantidad mensual de triages no atendidos.
- **Treemap por asegurador**: Titulado «TRIAGES NO REALIZADOS por ASEGURADOR»; distribución de los casos por asegurador.
- **Filtros**: Segmentadores de Año, Mes y ASEGURADOR, y botón de inicio que vuelve a CONSOLIDADO.

## Reglas de negocio
- **Triage no atendido**: Un turno cuenta si no existe ningún registro en HCNTRIAGE ligado a él (unión izquierda con HCNTRIAGE vacía).
- **Clasificaciones incluidas**: Solo turnos con HCNCONCOTRI entre 1 y 7. El significado de cada código está por confirmar.

## Observaciones
- **Asegurador por documento**: El asegurador se obtiene uniendo el turno con el paciente por número de documento (PlanillaUsuario AdmisionTriage); turnos sin documento quedan sin asegurador.
- **Promedio del año en curso**: El promedio mensual solo considera el año actual aunque los filtros muestren otros años.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
