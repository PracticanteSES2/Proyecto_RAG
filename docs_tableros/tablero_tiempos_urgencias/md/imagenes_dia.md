---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: IMAGENES DIA
nombre_funcional: Imágenes diagnósticas del día
bloque: Día
tablas: [IMAGENES DIA]
actualizado: 2026-10-20
version: 1
---

# IMAGENES DIA

## Propósito
Muestra el seguimiento de los estudios de imágenes diagnósticas solicitados en urgencias en cada etapa: solicitud, toma, lectura del radiólogo y resultado, para ver en qué etapa se demoran. Todos los tiempos están en horas. Se llega desde el botón de imágenes de RESUMEN_D y el botón superior izquierdo regresa a RESUMEN_D.

## Fuentes de datos
- **IMAGENES DIA**: Una solicitud de imagen diagnóstica por ingreso, hecha desde urgencias en los últimos 3 días; tabla en DirectQuery.

## Indicadores
- **Tiempo de toma**: Horas entre la solicitud y la toma del estudio (tmfecha); sin toma, hasta la hora actual. Columna IMAGENES DIA[TIEMPO_TOMA].
- **Tiempo de lectura**: Horas entre la toma (o la solicitud si no hay toma) y la lectura del radiólogo (FechaLecRadiologo); sin lectura, hasta la hora actual. Columna IMAGENES DIA[TIEMPO_LECTURA].
- **Tiempo de resultado de imágenes**: Horas entre la solicitud y la confirmación del resultado (HCRFECCONF); sin resultado, hasta la hora actual. Columna IMAGENES DIA[tiempo_respuesta].

## Visuales
- **Tabla en espera imágenes**: Estudios sin resultado confirmado con hasta 48 horas desde la solicitud. Columnas DOCUMENTO, PACIENTE, IMAGEN SOLICITADA, FECHA SOLICITUD, FECHA TOMA, FECHA LECTURA, FECHA RESULTADO, TIEMPO TOMA, TIEMPO LECTURA y TIEMPO RESULTADO.
- **Tabla imágenes tomadas últimas 24 horas**: Estudios con resultado confirmado en 24 horas o menos. Mismas columnas que la tabla de espera.

## Reglas de negocio
- **Sin semáforo**: Las tablas no tienen semáforo efectivo; sus reglas de color se refieren a TRIAGES_DIA[MIN], que no está en las tablas.
- **Solicitudes consideradas**: Solicitudes con registro en HCNRESSVFC (estudios de imágenes) hechas desde un folio del área de urgencias en los últimos 3 días.
- **Una fila por ingreso**: Se conserva una sola solicitud por ingreso, la primera según la fecha de confirmación del resultado y con las pendientes primero.

## Observaciones
- **Título de la tabla de tomadas**: El filtro no limita a las últimas 24 horas sino a los estudios con resultado en 24 horas o menos, solicitados en los últimos 3 días.
- **Sin leyenda ni semáforo**: A diferencia de las demás páginas del día, no hay leyenda de oportunidad ni semáforo. Por confirmar si se requiere.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
