---
tablero: DEMANDA INSATISFECHA
pagina: GENERAL
nombre_funcional: Demanda insatisfecha institucional por tipo de servicio
bloque: General
tablas: [TRIAGE, REFERENCIA, CIRUGÍAS, CITAS MEDICAS, SOLICITUD DE CAMAS, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# GENERAL

## Propósito
Mide la demanda que la institución no logró atender o resolver desde 2025: triages no realizados, pacientes de referencia no aceptados, cirugías, citas canceladas por causas institucionales y solicitudes de cama no asignadas. La página CONSOLIDADO resume los cinco componentes y lleva por botones a una página de análisis mensual de cada uno. Todas las páginas son de análisis histórico por año y mes.

## Fuentes de datos
- **Origen de los datos**: Consultas SQL al servidor de Dinámica Gerencial (bases DGEMPRES10 y PLANILLAUSUARIO) y, para referencia, a tablas de la bodega de datos (RECEPCIONES_DW). Cada página tiene su propia consulta.
- **Periodo cargado**: Todas las consultas traen registros desde el 1 de enero de 2025 hasta la fecha actual.
- **Asegurador**: Cada consulta trae el tercero (asegurador) del contrato del paciente; es la base de los gráficos y filtros por asegurador.

## Definiciones
- **Demanda insatisfecha**: Suma de triages no atendidos, pacientes de referencia no aceptados, cirugías (tabla CIRUGÍAS), citas canceladas y solicitudes de cama no asignadas. Medida TOTAL_DEMANDA_INSATISFECHA.
- **Triage no atendido**: Turno de triage registrado que no tiene registro de triage realizado asociado.
- **Paciente no aceptado (referencia)**: Solicitud de referencia de otra institución que el hospital no aceptó; se registra con una causa de no aceptación.
- **Cita cancelada**: Cita médica o de imágenes cancelada por una causa atribuible a la institución (daño o mantenimiento de equipo, falta de insumos, calamidad del especialista, error de habilitación, entre otras).
- **Solicitud de cama no asignada**: Solicitud de cama del paciente que egresó sin que se le asignara cama.
- **Promedio mensual**: Total del componente dividido por el número del mes actual (enero = 1); solo cuenta registros del año en curso.
- **Indicadores normalizados**: Relaciones por cada 100 o 1.000 eventos atendidos que muestra la página CONSOLIDADO (por ejemplo, no atendidos por cada 100 triages realizados).

## Reglas de negocio
- **Navegación**: CONSOLIDADO tiene botones TRIAGES, REFERENCIA, CIRUGÍAS, AMBULATORIO (página CITAS) y HOSPITALIZACIÓN (camas) (página SOLICITUD CAMAS); cada página de detalle tiene un botón de inicio para volver.
- **Filtros comunes**: Todas las páginas filtran por Año y Mes; las de detalle filtran además por asegurador.

## Observaciones
- **Nombres de página**: Los nombres de página en Power BI se toman de la documentación del propietario; nombres exactos por confirmar (no hay PBIP local de este tablero).
- **Página 6 ausente**: La documentación numera las páginas 1, 2, 3, 4, 5 y 7; por confirmar si existe una página 6 sin documentar.
- **Promedios con el mes actual**: Los promedios mensuales dividen por MONTH(TODAY()) aunque el usuario elija otro año o mes en los filtros; por confirmar si es el comportamiento deseado.
- **Medidas sin uso conocido**: Existen las medidas PROM_TRAMITES (REFERENCIA) y PROM_TRAMITES_CONTRA (tabla CONTRAREFERENCIA), sin visual documentado; por confirmar su uso.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
