---
tablero: TABLERO REFERENCIA
pagina: SEGUIMIENTO DE REMISION
nombre_funcional: Seguimiento de pacientes remitidos a otras instituciones
bloque: Histórico
tablas: [DETALLE_REMISIONES]
actualizado: 2026-10-20
version: 1
---

# SEGUIMIENTO DE REMISION

## Propósito
Hace seguimiento a los pacientes del hospital en proceso de remisión a otras instituciones: número de remisiones, tiempo promedio de respuesta, detalle por paciente, distribución por rango de tiempo y por EPS. Análisis histórico desde 2023 con filtro de fechas; se llega desde el botón REMISIÓN de INICIO. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **DETALLE_REMISIONES**: Todas las columnas de HISTORICO_REMISIONES_DW con fecha de registro entre el 1 de enero de 2023 y hoy. Incluye motivo, estado, servicio de origen (ServicioSes), EPS, fecha de remisión, fecha de aceptación y usuario que registra.

## Indicadores
- **Remisiones**: Número de remisiones en el filtro. Medida exacta por confirmar.
- **Tiempo promedio de respuesta**: Promedio del tiempo entre la remisión y su respuesta. Columna, cálculo y unidad por confirmar (probablemente horas).

## Visuales
- **Tarjetas**: REMISIONES y TIEMPO PROMEDIO RESPUESTA.
- **Filtros**: Segmentadores de ESTADO y EPS y control de rango de fechas.
- **Tabla de detalle**: Columnas MOTIVO, ESTADO, ServicioSes, EPS, FechaRemision y FECHACEPTACION, entre otras (la documentación menciona identificación y nombre del paciente).
- **Gráfico circular por tiempo**: Titulado «SOLICITUDES por TIEMPO»; remisiones por rango de horas (0-24, 24-72, más de 120 horas).
- **Gráfico circular por EPS**: Titulado «REMISIONES por EPS».

## Reglas de negocio
- **Nombre del usuario**: NOMBRE_COMPLETO une USU_NOMBRES y USU_APELLIDOS con un espacio.
- **Estados**: En la captura aparecen los estados Registrado, Aceptado Remision y Cancelado.

## Observaciones
- **Filtros documentados**: La documentación dice que los filtros son EPS, rango de edad y fechas, pero la captura muestra ESTADO, EPS y fechas. Por confirmar.
- **Rangos de tiempo sin documentar**: La columna de rangos de tiempo de esta tabla no está documentada. Por confirmar si usa los mismos cortes de REFERENCIA[RANGO_REMISION].
- **EPS con año**: Los nombres de EPS incluyen el año del contrato (por ejemplo «NUEVA EPS CONT 2026»), por lo que una misma EPS aparece varias veces en el gráfico.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
