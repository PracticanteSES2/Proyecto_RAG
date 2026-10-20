---
tablero: BRIEFING HOSPITALARIO
pagina: IMAGENES DIAGNOSTICAS
nombre_funcional: Imágenes diagnósticas tomadas y solicitudes de la semana por día, área y tramo horario
bloque: Día
tablas: [IMAGENES_TOMADAS, SOLICITUDES_RESPUESTA]
actualizado: 2026-10-20
version: 1
---

# IMAGENES DIAGNOSTICAS

## Propósito
Muestra las imágenes diagnósticas tomadas en la semana en curso frente a las solicitudes, el tiempo promedio de respuesta, las imágenes por área y el mapa de calor por tramo horario. Sirve para ver la carga del servicio de imágenes y sus horas pico. Se llega desde el botón DETALLE de la matriz IMAGENES TOMADAS POR TRAMO HORARIO en INICIO.

## Fuentes de datos
- **IMAGENES_TOMADAS**: Estudios de imágenes y apoyo diagnóstico realizados (servicios prestados de Dinámica) con cédula, cantidad, entidad, área de servicio, fecha, hora, tramo horario, examen, grupo, tipo de ingreso e ingreso. Periodo de la semana en curso.
- **SOLICITUDES_RESPUESTA**: Solicitudes de imágenes con el día de la semana (ORDEN_DIA). Consulta de origen por confirmar.

## Indicadores
- **Imágenes tomadas**: Número de estudios realizados. COUNT(IMAGENES_TOMADAS[ID_INGRESO]).
- **Solicitudes realizadas**: Solicitudes del mismo día de la semana. Medida Solicitudes_Con_Respuesta = CALCULATE(COUNTA(SOLICITUDES_RESPUESTA[OID_SOLICITUD]), FILTER(ALL(SOLICITUDES_RESPUESTA), ORDEN_DIA = MAX(IMAGENES_TOMADAS[ORDEN_DIA]))).
- **Tiempo promedio respuesta**: Promedio del tiempo de respuesta a las solicitudes. Cálculo, eventos y unidad por confirmar.

## Visuales
- **Tarjetas**: IMAGENES TOMADAS, SOLICITUDES REALIZADAS y TIEMPO PROMEDIO RESPUESTA.
- **Segmentadores**: AREA DE SERVICIO y TIPO DE INGRESO (ambulatorio u hospitalario).
- **Imágenes y solicitudes por día**: Columnas agrupadas CANTIDAD DE IMAGENES TOMADAS Y SOLICITUDES POR DÍA, con imágenes tomadas y solicitudes de cada fecha.
- **IMAGENES TOMADAS POR AREA DE SERVICIO**: Barras por área (por ejemplo rayos X, escanografía, ecografía, resonancia, mamografía, gastro, cardiología, medicina nuclear).
- **IMAGENES TOMADAS POR TRAMO HORARIO**: Matriz de imágenes por hora (filas) y fecha (columnas) con mapa de calor y totales.

## Reglas de negocio
- **Semana analizada**: Desde el viernes anterior al lunes de la semana actual hasta el final del sábado de la semana actual (SET DATEFIRST 1).
- **Áreas incluidas**: Cardiología (área 11, solo dos usuarios lectores definidos), área 0007 con médicos de especialidades 1, 2, 3, 4, 6 o 67, áreas 0010, 0012, 0013 y 0014, y áreas 0006, 0008, 0009 y 0058 con resultado confirmado o sin médico.
- **Exclusiones**: Ingresos anulados o en estado 4, servicios de honorarios, derechos, material y accesorios, y los códigos SES055 y S22227.
- **Gastro**: Las áreas cuyo nombre contiene «endoscop» se muestran como GASTRO.
- **Resultado confirmado**: En las áreas con lectura médica solo cuentan resultados confirmados (HCRCONFIR = 1).

## Observaciones
- **Conteo de imágenes**: La tarjeta cuenta filas (ID_INGRESO), no suma la cantidad (SERCANTID); un servicio con cantidad mayor a 1 cuenta una vez. Por confirmar si es lo esperado.
- **Medida mal nombrada**: Solicitudes_Con_Respuesta cuenta todas las solicitudes del día de la semana, no solo las respondidas. Por confirmar.
- **Códigos de área**: La documentación no traduce los códigos de área a nombres. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
