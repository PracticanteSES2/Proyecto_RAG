---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: CONSULTAS DIA
nombre_funcional: Oportunidad en la atención de consultas del día (triage II y III)
bloque: Día
tablas: [CONSULTAS_DIA, EN_ESPERA_CONSULTA]
actualizado: 2026-10-20
version: 1
---

# CONSULTAS DIA

## Propósito
Muestra en tiempo real la oportunidad de la consulta médica de urgencias, separada en triage II (mitad superior) y triage III (mitad inferior). En cada mitad hay una tabla de pacientes que esperan consulta y otra de pacientes ya atendidos, con semáforo. Se llega desde el botón de consulta de RESUMEN_D y el botón superior izquierdo regresa a RESUMEN_D.

## Fuentes de datos
- **CONSULTAS_DIA**: Triages de hoy con su admisión y su primer folio de historia clínica; tabla en DirectQuery.
- **EN_ESPERA_CONSULTA**: Ingresos de hoy que todavía no tienen folio de consulta; tabla en DirectQuery.

## Indicadores
- **Tiempo de espera para consulta**: Minutos entre la admisión (AINFECING) y el primer folio de historia clínica (inicio de la consulta). Columna CONSULTAS_DIA[TIEMPO_ESPERA_CONS].
- **Tiempo en espera de consulta**: Minutos desde la admisión hasta el momento en que se consulta la página, para pacientes sin folio. Columna EN_ESPERA_CONSULTA[TIEMPO_ESPERA_CONSUL].

## Visuales
- **Tabla en espera consulta triage II**: Pacientes de triage II sin consulta con documento, nombre, tiempo en espera y triage asignado. Filtro TRIAGE_II = 1.
- **Tabla pacientes atendidos triage II**: Titulada «CONSULTAS REALIZADAS»; pacientes de triage II con hora de admisión, hora de consulta y tiempo de espera. Filtros TRIAGE_II = 1 y hora de consulta no vacía.
- **Tabla en espera consulta triage III**: Igual que la de triage II con el filtro TRIAGE_III = 1 (códigos III e IIIU).
- **Tabla pacientes atendidos triage III**: Igual que la de triage II con el filtro TRIAGE_III = 1.
- **Leyendas de oportunidad**: Textos sobre cada mitad con los rangos del semáforo de triage II y de triage III.

## Reglas de negocio
- **Semáforo triage II**: Verde de 0 a 15 minutos, amarillo de 16 a 30 y rojo de 31 o más.
- **Semáforo triage III**: Verde de 0 a 60 minutos, amarillo de 61 a 90 y rojo de 91 o más.
- **Marca de triage II**: TRIAGE_II vale 1 solo para el código II; IIP e IIS no entran en las tablas de triage II.
- **Marca de triage III**: TRIAGE_III vale 1 para los códigos III e IIIU.
- **Paciente en espera de consulta**: Ingreso de hoy, triage no confirmado (HCTCONFIR = 0) de las clasificaciones 2, 7, 9, 16, 17, 18 o 19 y sin ningún folio todavía.
- **Ingresos anulados**: CONSULTAS_DIA solo trae triages de hoy con ingreso de estado distinto de 2 (AINESTADO).
- **Triages fuera de esta página**: Los triages IV y V se atienden por consulta prioritaria (página CONSULTAS PRIORITARIAS).

## Observaciones
- **IIP e IIS excluidos**: Los códigos IIP e IIS se muestran como II pero no aparecen en las tablas de triage II. Por confirmar si deben incluirse.
- **Huecos en el semáforo**: En las tablas de atendidos de triage II los valores exactos de 16 y 31 minutos quedan sin color.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
