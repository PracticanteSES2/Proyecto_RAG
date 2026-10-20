---
tablero: TABLERO EPS
pagina: DISPERSIÓN DÍA
nombre_funcional: Atendidos frente a llegadas por tramo horario del día actual
bloque: Día
tablas: [DISPERSION_DIA]
actualizado: 2026-10-20
version: 1
---

# DISPERSIÓN DÍA

## Propósito
Gráfico de dispersión del día en curso que compara, por tramo horario, los pacientes atendidos en triage con las llegadas a urgencias. Sirve para el seguimiento en tiempo real del balance entre demanda y capacidad. Página de navegación desde la vista de dispersión.

## Fuentes de datos
- **Consulta de llegadas y atendidos del día**: Por cada hora de hoy cuenta los triages realizados (HCNTRIAGE, campo HCTFECTRI) y las llegadas (ADMISIONTRIAGE, campo HoraEntrada), y calcula pendientes por tramo y acumulados.

## Indicadores
- **Atendidos por tramo**: Triages realizados hoy en cada hora (ATENDIDOS). Unidad: pacientes.
- **Llegadas por tramo**: Llegadas registradas hoy en cada hora (LLEGADAS). Unidad: pacientes.
- **Pendientes por tramo**: LLEGADAS menos ATENDIDOS de la hora (PENDIENTES_TRAMO). Unidad: pacientes.
- **Pendientes acumulados**: Suma acumulada de pendientes desde el inicio del día, mostrada en 0 si es negativa (PENDIENTES_ACUMULADOS). Unidad: pacientes.

## Visuales
- **Filtros de segmentación**: Listas de Año, Mes, Día y ASEGURADORA.
- **Dispersión atendidos y llegadas por tramo**: Titulado «ATENDIDOS y LLEGADAS por TRAMO»; eje X ATENDIDOS, eje Y LLEGADAS y un punto de color por hora del día (leyenda TRAMO).
- **Líneas guía**: Una línea vertical y otra horizontal punteadas que dividen el gráfico en cuadrantes de equilibrio.
- **Botón VOLVER**: Regresa a la página anterior.

## Reglas de negocio
- **Solo el día actual**: Atendidos y llegadas se filtran a la fecha de hoy (GETDATE).
- **Tramo horario**: La hora se trunca a la hora en punto; las horas sin llegadas o sin atenciones quedan con 0.
- **Piso de pendientes acumulados**: Si la suma acumulada de pendientes es negativa se muestra 0.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Filtros sin efecto**: La consulta solo trae el día de hoy y no incluye aseguradora; los filtros de Año, Mes, Día y ASEGURADORA no deberían cambiar el gráfico. Por confirmar.
- **Valor de las líneas guía**: Por confirmar qué valor marcan las líneas punteadas.
- **Origen de la navegación**: La documentación no dice desde qué botón se llega a esta página. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
