---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: LABORATORIOS
nombre_funcional: Laboratorios del día
bloque: Día
tablas: [LABORATORIOS_DIA]
actualizado: 2026-10-20
version: 1
---

# LABORATORIOS

## Propósito
Muestra la oportunidad de los resultados de laboratorio solicitados en urgencias: exámenes que esperan resultado y exámenes solicitados hoy que ya tienen resultado, con el tiempo hasta el resultado en minutos y semáforo. Se llega desde el botón de laboratorios de RESUMEN_D y el botón superior izquierdo regresa a RESUMEN_D.

## Fuentes de datos
- **LABORATORIOS_DIA**: Una solicitud de laboratorio por ingreso, hecha desde urgencias en los últimos 3 días; tabla en DirectQuery.

## Indicadores
- **Tiempo de resultado de laboratorio**: Minutos entre la solicitud del examen (HCSFECSOL) y el resultado (HCRFECRES); si está pendiente, hasta la hora actual. Columna LABORATORIOS_DIA[TIEMPO_RESULTADO].

## Visuales
- **Leyenda de oportunidad**: Texto con los rangos del semáforo: 0-90 minutos, 91-120 minutos y 120 minutos o más.
- **Tabla en espera laboratorios**: Exámenes sin resultado con menos de 1.440 minutos (24 horas) desde la solicitud. Columnas DOCUMENTO, NOMBRE PACIENTE, EXAMEN, FECHA SOLICITUD, FECHA RESULTADO y TIEMPO RESULTADO.
- **Tabla laboratorios últimas 24 horas**: Exámenes con resultado cuya fecha de solicitud es hoy. Mismas columnas que la tabla de espera.

## Reglas de negocio
- **Semáforo de laboratorios**: En ambas tablas, verde de 0 a 90 minutos, amarillo de más de 90 hasta 120 y rojo de más de 120.
- **Solicitudes consideradas**: Exámenes del área de laboratorio (área 15) pedidos desde un folio del área de urgencias (área 2) en los últimos 3 días.
- **Una fila por ingreso**: Se conserva una sola solicitud por ingreso, la primera según la fecha de resultado y con las pendientes primero; un paciente con varios exámenes aparece una vez, con el pendiente si lo tiene.

## Observaciones
- **Título de la tabla de resultados**: El filtro es fecha de solicitud igual a hoy, no las últimas 24 horas.
- **Un examen por paciente**: La página no muestra todos los exámenes de cada paciente sino uno. Por confirmar si es el comportamiento esperado.
- **Leyenda y regla de 120 minutos**: La leyenda dice «120 minutos o más», pero el rojo empieza en más de 120; el valor exacto 120 queda en amarillo.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
