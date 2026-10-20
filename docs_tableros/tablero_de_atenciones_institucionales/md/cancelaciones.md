---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: CANCELACIONES
nombre_funcional: Cirugías canceladas por mes y por asegurador
bloque: Histórico
tablas: [CIRUGIAS_PENDIENTES, Calendario]
actualizado: 2026-10-20
version: 1
---

# CANCELACIONES

## Propósito
Muestra cuántas cirugías programadas se cancelan cada mes y con qué asegurador, para hacer seguimiento a las cancelaciones del servicio quirúrgico. Se llega desde el botón CANCELACIONES de la página CIRUGÍAS.

## Fuentes de datos
- **Solicitudes de cirugía**: Solicitudes de cirugía programada (TipoCirugiaOid = 1) planeadas desde 2025-01-01, con paciente, EPS, especialidad, procedimientos, médico, estado actual y la primera fecha de cada estado quirúrgico. FECHA es la fecha en que se planeó. Tabla del modelo por confirmar (CIRUGIAS_PENDIENTES u OPORTUNIDAD CIRUGIA, que traen las mismas columnas).

## Indicadores
- **Cirugías canceladas**: Número de solicitudes canceladas. Cálculo por confirmar (conteo de solicitudes con estado cancelado).

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes y ESPECIALIDAD.
- **Gráfico de cirugías canceladas**: Líneas «CIRUGÍAS CANCELADAS» con el conteo mensual de cancelaciones, una línea por año.
- **Tabla de cirugías canceladas**: Matriz de cancelaciones por año (filas) y mes (columnas).
- **Gráfico de canceladas por asegurador**: Barras horizontales «CIRUGÍAS CANCELADAS POR ASEGURADOR» con el conteo por asegurador, de mayor a menor.
- **Botón de inicio**: Botón de casa que vuelve a INICIO.

## Reglas de negocio
- **Periodo**: Solo entran solicitudes planeadas desde el 2025-01-01 (fecha fija en la consulta).
- **Fecha de cancelación**: La fecha del estado «Paciente Cancelado» es la primera vez que la solicitud pasó al estado 8.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Misma consulta que PENDIENTES**: La documentación usa la misma consulta para CANCELACIONES y PENDIENTES y no indica el filtro que separa las canceladas. Por confirmar si se filtra por ESTADO ACTUAL o por la fecha de «Paciente Cancelado».
- **Rótulos de eje**: En la captura, el eje del gráfico de líneas y el de barras dicen «PENDIENTES» aunque muestran cancelaciones.
- **Periodo descrito**: La documentación dice «desde el año anterior hasta la fecha», pero la consulta tiene la fecha fija 2025-01-01.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
