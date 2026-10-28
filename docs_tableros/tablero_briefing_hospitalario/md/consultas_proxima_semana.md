---
tablero: BRIEFING HOSPITALARIO
pagina: CONSULTAS PRÓXIMA SEMANA
nombre_funcional: Citas asignadas para los próximos días y digiturnos por tramo horario
bloque: Día
tablas: [BI_PROXIMAS_CITAS, AMBULATORIO_SS]
actualizado: 2026-10-20
version: 1
---

# CONSULTAS PRÓXIMA SEMANA

## Propósito
Muestra las citas ya asignadas desde mañana en adelante, separadas en consulta ambulatoria e imágenes diagnósticas, por fecha y por tramo horario, junto con el histórico de digiturnos asignados. Sirve para anticipar horas de alta demanda y evitar sobrecupos. Se llega desde el botón DETALLE de la matriz CONSULTAS PRÓXIMA SEMANA en INICIO.

## Fuentes de datos
- **BI_PROXIMAS_CITAS**: Citas asignadas para los próximos días (consulta SELECT * FROM BI_PROXIMAS_CITAS) con tipo de consulta, especialidad, fecha y tramo horario; nombre de la tabla en el modelo por confirmar.
- **AMBULATORIO_SS**: Citas usadas por la matriz de INICIO (fecha, tramo horario y cita).
- **Digiturnos**: Fuente del histórico de digiturnos no documentada. Por confirmar.

## Indicadores
- **Consultas ambulatorias**: Citas de consulta ambulatoria asignadas. Cálculo por confirmar.
- **Consultas imágenes**: Citas de imágenes diagnósticas asignadas. Cálculo por confirmar.
- **Citas por tramo**: Número de citas en cada hora del día. En INICIO es COUNT(AMBULATORIO_SS[CITA]).
- **Digiturnos asignados**: Turnos de digiturno entregados por tipo y por tramo horario. Cálculo por confirmar.

## Visuales
- **Tarjetas**: CONSULTAS AMBULATORIAS y CONSULTAS IMÁGENES.
- **Segmentadores**: ESPECIALIDAD CONSULTA, ESPECIALIDAD IMÁGENES, AÑO TURNOS y MES TURNOS.
- **CONSULTAS PROXIMA SEMANA**: Columnas por fecha con dos series, CONSULTA AMBULATORIA e IMAGENES, y botones para elegir el tipo.
- **DIGITURNOS POR TIPO**: Barras con los turnos asignados por tipo de turno (por ejemplo EPS EFECTIVO, MEDICINA PREPAGADA, PRIORIZADOS).
- **Matriz CONSULTAS PRÓXIMA SEMANA**: Citas por tramo horario (filas) y fecha (columnas) con escala de color verde a rojo.
- **Histórico de digiturnos**: Matriz titulada HISTORICO DE DIGITURNOS ASIGNADOS POR TRAMO HORARIO con turnos por tramo horario y día de la semana (lunes a sábado) con totales y escala de color.

## Reglas de negocio
- **Desde mañana**: Las citas mostradas son las agendadas desde el día siguiente a la fecha de consulta del tablero.

## Observaciones
- **Realizadas o asignadas**: La documentación dice «consultas realizadas semanalmente», pero la página muestra citas asignadas a futuro.
- **Horizonte**: El nombre dice próxima semana, pero el número de días incluidos depende de BI_PROXIMAS_CITAS. Por confirmar.
- **Escala de color**: Las matrices usan escala de color sin umbrales documentados.
- **Nombre de página**: La página no está en la copia local del PBIP. Nombre de página en Power BI por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
