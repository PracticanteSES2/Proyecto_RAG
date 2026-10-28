---
tablero: TABLERO REFERENCIA
pagina: DETALLE NO ACEPTADOS RECEPCION
nombre_funcional: Detalle de solicitudes de referencia no aceptadas
bloque: Día
tablas: [REFERENCIA]
actualizado: 2026-10-20
version: 1
---

# DETALLE NO ACEPTADOS RECEPCION

## Propósito
Lista las solicitudes de referencia que no fueron aceptadas en la recepción en los últimos 30 días, con la causa, la fecha de solicitud y de respuesta, el tiempo de respuesta y la EPS. Seguimiento reciente (bloque Día); se llega desde el botón NO ACEPTADOS RECEPCIÓN de INICIO. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **REFERENCIA**: La misma tabla de INICIO (solicitudes de recepción con llamada en los últimos 30 días).

## Indicadores
- **Cantidad de solicitudes**: Número de solicitudes no aceptadas en el filtro. Medida exacta por confirmar.
- **Tiempo promedio de respuesta**: Promedio en horas de REFERENCIA[TIEMPO_REMISION]; para un no aceptado es el tiempo entre la llamada y el rechazo. Agregación por confirmar.
- **Promedio de edad**: Promedio en años de REFERENCIA[ANOS]. Agregación por confirmar.

## Visuales
- **Tarjetas**: CANTIDAD DE SOLICITUDES, TIEMPO PROMEDIO RESPUESTA y PROMEDIO DE EDAD.
- **Filtros**: Segmentadores de EPS y RANGO EDAD y control de rango de fechas.
- **Tabla de detalle**: Columnas IDENTIFICACIÓN, NOMBRE, CAUSA, FECHA SOLICITUD, FECHA RESPUESTA y EPS.
- **Gráfico circular por rango de remisión**: Titulado «SOLICITUDES por RANGO_REMISION»; solicitudes por rango de tiempo de respuesta.
- **Gráfico circular por EPS**: Titulado «SOLICITUDES por EPS».
- **Botón de navegación**: SEGUIMIENTO RECEPCIÓN lleva a SEGUIMIENTO DE RECEPCION; el botón de inicio vuelve a INICIO.

## Reglas de negocio
- **Solicitud no aceptada**: Por confirmar el filtro exacto de la página; en la captura de la documentación todas las filas tienen causa de no aceptación (por ejemplo ACEPTADO POR OTRA INSTITUCIÓN o NO DISPONIBILIDAD DE CAMA).
- **Fecha de respuesta**: Es la fecha de no aceptación (última edición al estado 3). Por confirmar.

## Observaciones
- **Suma con aceptados**: En las capturas de la documentación, las solicitudes de esta página más las de DETALLE ACEPTADOS RECEPCION igualan el total de INICIO; parece que la página filtra «con causa» y la de aceptados «sin causa». Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
