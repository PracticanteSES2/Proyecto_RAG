---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: IMAGENES
nombre_funcional: Imágenes diagnósticas, histórico
bloque: Histórico
tablas: [IMAGENES]
actualizado: 2026-10-20
version: 1
---

# IMAGENES

## Propósito
Muestra por año y mes la cantidad de imágenes diagnósticas con resultado y el tiempo promedio de respuesta en minutos. Se llega desde RESUMEN.

## Fuentes de datos
- **IMAGENES**: Una imagen diagnóstica con resultado confirmado por ingreso, solicitada desde urgencias desde el 01/01/2023; FECHA es la fecha de la solicitud; tabla en Import.

## Indicadores
- **Imágenes tomadas**: Número de imágenes con resultado. SUM(IMAGENES[SOLICITUDES_CANT]) en la tarjeta y DISTINCTCOUNT(IMAGENES[OID_SOLICITUD]) en el gráfico.
- **Tiempo promedio de respuesta de imágenes**: Minutos entre la solicitud y la confirmación del resultado. AVERAGE(IMAGENES[tiempo_respuesta]).

## Visuales
- **Segmentadores de fecha**: Año, Mes y Día sobre la jerarquía de Calendario[FECHA]; filtran por la fecha de la solicitud.
- **Tarjetas de imágenes y tiempo**: Imágenes tomadas y tiempo promedio de respuesta en minutos.
- **Gráfico de imágenes y tiempo por mes**: Columnas IMÁGENES TOMADAS y línea TIEMPO PROMEDIO DE RESPUESTA en minutos, por año y mes.
- **Botón de regreso**: Lleva a RESUMEN.

## Reglas de negocio
- **Solicitudes consideradas**: Solicitudes con confirmación de resultado en HCNRESSVFC, desde folios del área de urgencias, con una fila por ingreso.
- **Unidad distinta al día**: El tiempo de respuesta histórico está en minutos; en IMAGENES DIA está en horas.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
