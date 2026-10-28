---
tablero: TABLERO REFERENCIA
pagina: DETALLE ACEPTADOS RECEPCION
nombre_funcional: Detalle de solicitudes de referencia aceptadas
bloque: Día
tablas: [REFERENCIA]
actualizado: 2026-10-28
version: 2
---

# DETALLE ACEPTADOS RECEPCION

## Propósito
Lista las solicitudes de referencia de los últimos 30 días en estado Aceptado, Con Ingreso, Tramite Por SES o Es Urgencia Vital (es decir, no rechazadas), con motivo, fecha de solicitud, de ingreso y de aceptación, y su EPS. Seguimiento reciente (bloque Día); se llega desde el botón ACEPTADOS RECEPCIÓN de INICIO. En Power BI la página se llama DETALLE ACEPTADOS RECEPCION.

## Fuentes de datos
- **REFERENCIA**: La misma tabla de INICIO (solicitudes de recepción con llamada en los últimos 30 días).

## Indicadores
- **Cantidad de solicitudes**: Número de solicitudes de la página en el filtro. Medida exacta por confirmar.
- **Tiempo promedio de respuesta**: Promedio en horas de REFERENCIA[TIEMPO_REMISION]; para aceptadas es el tiempo entre la llamada y la aceptación, y para las que no tienen respuesta, hasta hoy. Agregación por confirmar.
- **Promedio de edad**: Promedio en años de REFERENCIA[ANOS]. Agregación por confirmar.

## Visuales
- **Tarjetas**: CANTIDAD DE SOLICITUDES, TIEMPO PROMEDIO RESPUESTA y PROMEDIO DE EDAD.
- **Filtros**: Segmentadores de EPS y RANGO EDAD y control de rango de fechas.
- **Tabla de detalle**: Columnas IDENTIFICACIÓN, NOMBRE, MOTIVO, FECHA SOLICITUD, FECHA INGRESO, FECHA ACEPTADO y EPS.
- **Gráfico circular por tiempo**: Titulado «SOLICITUDES por TIEMPO»; solicitudes por rango de tiempo de respuesta.
- **Gráfico circular por EPS**: Titulado «SOLICITUDES por EPS».
- **Botón de navegación**: SEGUIMIENTO RECEPCIÓN lleva a DETALLE_RECEPCIONES; el botón de inicio vuelve a INICIO.

## Reglas de negocio
- **Solicitudes incluidas**: La página filtra REFERENCIA[ESTADO] en Aceptado, Con Ingreso, Tramite Por SES y Es Urgencia Vital; en la captura de la documentación aparecen filas con fecha de aceptación y filas sin ella (con motivo como no disponibilidad de la especialidad).

## Observaciones
- **Descripción copiada**: La documentación del propietario describe esta página con el mismo texto de no aceptados («solicitudes que no fueron aceptadas»); el contenido real muestra aceptadas y pendientes.
- **Fechas de ingreso ficticias**: En la captura de la documentación FECHA INGRESO muestra 31/12/1969 o 01/01/1900 cuando el paciente no ha ingresado; son valores por defecto del origen, no fechas reales.
- **Tiempo promedio alto**: Las solicitudes sin respuesta suman horas hasta hoy y elevan el promedio (314,80 horas en la captura de la documentación frente a 9,77 en no aceptados).

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
