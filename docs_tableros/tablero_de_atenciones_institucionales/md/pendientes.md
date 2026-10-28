---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: PENDIENTES
nombre_funcional: Cirugías pendientes por mes, asegurador y causa
bloque: Histórico
tablas: [CIRUGIAS_PENDIENTES, Calendario]
actualizado: 2026-10-28
version: 2
---

# PENDIENTES

## Propósito
Muestra las cirugías programadas que siguen pendientes, por mes, por asegurador y por causa (estado en que están detenidas). Sirve para ver dónde se acumulan las solicitudes. Se llega desde el botón PENDIENTES de la página CIRUGÍAS.

## Fuentes de datos
- **CIRUGIAS_PENDIENTES**: Solicitudes de cirugía programada (TipoCirugiaOid = 1) planeadas desde 2025-01-01, con paciente, EPS, especialidad, procedimientos agrupados, médico, ESTADO ACTUAL y la primera fecha de cada estado quirúrgico. FECHA es la fecha en que se planeó.

## Indicadores
- **Cirugías pendientes**: Número de solicitudes pendientes. Cálculo por confirmar (conteo de solicitudes en estados no finales).

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes y ESPECIALIDAD.
- **Gráfico de cirugías pendientes**: Líneas con el conteo mensual de pendientes por año (título en la captura «CIRUGÍASPENDIENTES»).
- **Tabla de cirugías pendientes**: Matriz de pendientes por año (filas) y mes (columnas).
- **Gráfico de pendientes por asegurador**: Barras «CIRUGÍAS PENDIENTES POR ASEGURADOR» con el conteo por asegurador.
- **Gráfico de pendientes por causa**: Barras «CIRUGÍAS PENDIENTES POR CAUSA» con el conteo por estado actual, por ejemplo espera preanestésico, espera programación, paciente para junta, trámite clínico/ADM, documentación entregada, por autorizar y consulta externa.
- **Botón de inicio**: Botón de casa que vuelve a INDICADORES.

## Reglas de negocio
- **Causa de pendiente**: La causa es el estado actual de la solicitud (ESTADO ACTUAL, nombre del estado en Qx_EstadosQuirofano).
- **Procedimientos agrupados**: Si una solicitud tiene varios procedimientos, se muestran en un solo texto separados por « * ».
- **Periodo**: Solo entran solicitudes planeadas desde el 2025-01-01 (fecha fija en la consulta).

## Observaciones
- **Nombre de página**: Coincide con la página PENDIENTES del PBIP.
- **Definición de pendiente**: La documentación no dice qué estados cuentan como pendientes ni qué filtro aplica la página. Por confirmar.
- **Estados de causa**: Algunas causas de la captura (paciente para junta, paciente autorizado) no están entre los 14 estados cuya fecha guarda la consulta; vienen del estado actual.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
