---
tablero: DEMANDA INSATISFECHA
pagina: GENERAL
nombre_funcional: Demanda insatisfecha institucional por tipo de servicio
bloque: General
tablas: [TRIAGE, REFERENCIA, CIRUGÍAS, CITAS MEDICAS, SOLICITUD DE CAMAS, CALENDARIO]
actualizado: 2026-10-28
version: 2
---

# GENERAL

## Propósito
Mide la demanda que la institución no logró atender o resolver desde 2025: triages no realizados, pacientes de referencia no aceptados, cirugías, citas canceladas por causas institucionales y solicitudes de cama no asignadas. La página CONSOLIDADO resume los cinco componentes y lleva por botones a una página de análisis mensual de cada uno. Todas las páginas son de análisis histórico por año y mes.

## Fuentes de datos
- **Origen de los datos**: Consultas SQL al servidor de Dinámica Gerencial (bases DGEMPRES10 y PLANILLAUSUARIO) y, para referencia, a tablas de la bodega de datos (RECEPCIONES_DW). Cada página tiene su propia consulta.
- **Periodo cargado**: Todas las consultas traen registros desde el 1 de enero de 2025 hasta la fecha actual.
- **Asegurador**: Cada consulta trae el tercero (asegurador) del contrato del paciente; es la base de los gráficos y filtros por asegurador.

## Definiciones
- **Demanda insatisfecha**: Suma de triages no atendidos, pacientes de referencia no aceptados, cirugías no oportunas, citas canceladas por la institución y solicitudes de cama no asignadas. Medida TOTAL_DEMANDA_INSATISFECHA.
- **Triage no atendido**: Turno de triage registrado que no tiene registro de triage realizado asociado.
- **Paciente no aceptado (referencia)**: Solicitud de referencia de otra institución que el hospital no aceptó; se registra con una causa de no aceptación.
- **Cita cancelada**: Cita médica o de imágenes cancelada por una causa atribuible a la institución (daño o mantenimiento de equipo, falta de insumos, calamidad del especialista, error de habilitación, entre otras).
- **Solicitud de cama no asignada**: Solicitud de cama del paciente que egresó sin que se le asignara cama.
- **Promedio mensual**: Total del componente dividido por el número del mes actual (enero = 1); solo cuenta registros del año en curso.
- **Indicadores normalizados**: Relaciones por cada 100 o 1.000 eventos atendidos que muestra la página CONSOLIDADO (por ejemplo, no atendidos por cada 100 triages realizados).
- **Cirugía no oportuna**: Solicitud de cirugía programada con más de 45 días entre quedar en espera de programación y llegar a sala de espera (o hasta hoy); la oportuna tiene 45 días o menos.

## Reglas de negocio
- **Navegación**: CONSOLIDADO tiene botones TRIAGES, REFERENCIA, CIRUGÍAS, AMBULATORIO (página CITAS) y HOSPITALIZACIÓN (camas) (página SOLICITUD CAMAS); cada página de detalle tiene un botón de inicio para volver.
- **Filtros comunes**: Todas las páginas filtran por Año y Mes; las de detalle filtran además por asegurador.
- **Filtros de página**: Cada componente se limita con filtros de página (referencia por causa, cirugías de más de 45 días sin ANESTESIOLOGIA ni JUNTA MEDICA, citas por causa de cancelación y camas de cinco servicios); el detalle está en CONSOLIDADO y en cada página.

## Observaciones
- **Nombres de página**: Los nombres de página son los del PBIP: CONSOLIDADO, TRIAGES, REFERENCIA, CIRUGÍAS, CITAS y SOLICITUD CAMAS; solo CONSOLIDADO es visible y las demás son páginas ocultas a las que se llega por botón.
- **Página 6 ausente**: La documentación numera las páginas 1, 2, 3, 4, 5 y 7 y el PBIP trae seis páginas; la tabla CONTRAREFERENCIA y la medida PROM_TRAMITES_CONTRA no tienen página, por lo que la página 6 podría ser de contrarreferencia. Por confirmar.
- **Promedios con el mes actual**: Los promedios mensuales dividen por MONTH(TODAY()) aunque el usuario elija otro año o mes en los filtros; por confirmar si es el comportamiento deseado.
- **Medidas sin uso conocido**: Las medidas PROM_TRAMITES_CONTRA y %CIRUGIAS, %CITAS, %REFERENCIA y %TRIAGE no están en ningún visual del PBIP; PROM_TRAMITES sí alimenta el promedio de REFERENCIA.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
