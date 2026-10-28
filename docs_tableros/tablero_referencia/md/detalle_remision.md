---
tablero: TABLERO REFERENCIA
pagina: DETALLE REMISION
nombre_funcional: Seguimiento de pacientes remitidos a otras instituciones
bloque: Histórico
tablas: [DETALLE_REMISIONES, CONTRARREFERENCIA]
actualizado: 2026-10-28
version: 2
---

# DETALLE REMISION

## Propósito
Hace seguimiento a los pacientes del hospital en proceso de remisión a otras instituciones: número de remisiones, tiempo promedio de respuesta, detalle por paciente, distribución por rango de tiempo y por EPS. Análisis histórico desde 2023 con filtro de fechas; se llega desde el botón REMISIÓN de INICIO. La documentación del propietario la llama SEGUIMIENTO DE REMISION; en el informe existe además la página SEGUIMIENTOS REMISION (bitácora de anotaciones). Por confirmar qué visual está en cada una.

## Fuentes de datos
- **CONTRARREFERENCIA**: Remisiones (SEGUIMIENTO_REMISIONES_DW) con ingreso en los últimos 90 días. Incluye motivo, estado (probable), servicio de origen (ServicioSes), EPS (EPS_PACIENTE), fecha de remisión, fecha de aceptación (FECHACEPTACION), TIEMPO_RESPUESTA y RANGO_TIEMPO.
- **DETALLE_REMISIONES**: Anotaciones de seguimiento de cada remisión (HISTORICO_REMISIONES_DW) con fecha de registro entre el 1 de enero de 2023 y hoy; se une a CONTRARREFERENCIA por OidRemision. Incluye descripción, alerta, verificación y usuario que registra.

## Indicadores
- **Remisiones**: Número de remisiones en el filtro. Medida exacta por confirmar.
- **Tiempo promedio de respuesta**: Promedio en horas de CONTRARREFERENCIA[TIEMPO_RESPUESTA] (desde la fecha de remisión hasta la aceptación, o hasta hoy si no hay). Agregación por confirmar.

## Visuales
- **Tarjetas**: REMISIONES y TIEMPO PROMEDIO RESPUESTA.
- **Filtros**: Segmentadores de ESTADO y EPS y control de rango de fechas.
- **Tabla de detalle**: Columnas de CONTRARREFERENCIA: MOTIVO, ESTADO, ServicioSes, EPS, FechaRemision y FECHACEPTACION, entre otras (la documentación menciona identificación y nombre del paciente).
- **Gráfico circular por tiempo**: Titulado «SOLICITUDES por TIEMPO»; remisiones según CONTRARREFERENCIA[RANGO_TIEMPO] (0-24, 24-72, 72-120 y más de 120 horas).
- **Gráfico circular por EPS**: Titulado «REMISIONES por EPS».

## Reglas de negocio
- **Nombre del usuario**: DETALLE_REMISIONES[NOMBRE_COMPLETO] une USU_NOMBRES y USU_APELLIDOS con un espacio.
- **Rangos de tiempo**: CONTRARREFERENCIA[RANGO_TIEMPO] usa los cortes 0-24, 24-72, 72-120 y más de 120 horas, los mismos de REFERENCIA[RANGO_REMISION]; queda en blanco si el tiempo es negativo.
- **Estados**: En la captura aparecen los estados Registrado, Aceptado Remision y Cancelado.

## Observaciones
- **Filtros documentados**: La documentación dice que los filtros son EPS, rango de edad y fechas, pero la captura muestra ESTADO, EPS y fechas. Por confirmar.
- **Tabla de la documentación**: La documentación original describe la consulta de DETALLE_REMISIONES, pero el detalle por EPS, fechas y rangos corresponde a CONTRARREFERENCIA. Por confirmar.
- **Filtro de página**: DETALLE REMISION y SEGUIMIENTOS REMISION filtran por REFERENCIA[ESTADO], tabla sin relación con las de remisión; por confirmar si el filtro tiene efecto.
- **EPS con año**: Los nombres de EPS incluyen el año del contrato (por ejemplo «NUEVA EPS CONT 2026»), por lo que una misma EPS aparece varias veces en el gráfico.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
