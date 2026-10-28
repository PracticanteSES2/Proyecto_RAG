---
tablero: TABLERO REFERENCIA
pagina: DETALLE_RECEPCIONES
nombre_funcional: Bitácora de seguimiento de las solicitudes recibidas
bloque: Día
tablas: [REFERENCIA, DETALLE_RECEPCIONES]
actualizado: 2026-10-28
version: 2
---

# DETALLE_RECEPCIONES

## Propósito
Muestra la bitácora de cada solicitud de referencia recibida: las anotaciones de seguimiento (llamadas, validaciones clínicas, trámites administrativos, autorizaciones, ingreso) por paciente. Sirve para dar trazabilidad a los casos. Seguimiento reciente (bloque Día); se llega desde el botón SEGUIMIENTO RECEPCIÓN de las páginas de detalle. La documentación del propietario la llama SEGUIMIENTO DE RECEPCION.

## Fuentes de datos
- **REFERENCIA**: Solicitudes de recepción de los últimos 30 días; da la identificación, el nombre, la EPS y el estado.
- **DETALLE_RECEPCIONES**: Anotaciones de seguimiento (OBSERVACIONES_RECEPCION_DW con el nombre del usuario que registra, desde DIM_USUARIOS), con fecha de registro desde el 1 de enero de 2023; se une a REFERENCIA por RecepcionSegOid = OID (columna Descripcion).

## Indicadores
- **Cantidad de solicitudes**: Número de solicitudes en el filtro. Medida exacta por confirmar.
- **Tiempo promedio de respuesta**: Promedio en horas de REFERENCIA[TIEMPO_REMISION]. Agregación por confirmar.
- **Promedio de edad**: Promedio en años de REFERENCIA[ANOS]. Agregación por confirmar.

## Visuales
- **Tarjetas**: CANTIDAD DE SOLICITUDES, TIEMPO PROMEDIO RESPUESTA y PROMEDIO DE EDAD.
- **Filtros**: Segmentadores de EPS y DOCUMENTO y control de rango de fechas.
- **Tabla de pacientes y descripciones**: Columnas IDENTIFICACIÓN, NOMBRE y Descripcion; una fila por anotación de seguimiento, por lo que un paciente puede tener varias filas.
- **Botones de navegación**: NO ACEPTADOS RECEPCIÓN y ACEPTADOS RECEPCIÓN; el botón de inicio vuelve a INICIO.

## Reglas de negocio
- **Estados incluidos**: La página filtra REFERENCIA[ESTADO] en los cinco estados (Aceptado, Con Ingreso, Es Urgencia Vital, No Aceptado y Tramite Por SES).
- **Quién registra**: DETALLE_RECEPCIONES[NOMBRE_REGISTRA] es el nombre en mayúsculas del usuario que registra la anotación.

## Observaciones
- **Filtros documentados**: La documentación dice que los filtros son EPS, rango de edad y fechas, pero la captura muestra EPS, DOCUMENTO y fechas. Por confirmar.
- **Texto libre clínico**: Las descripciones son texto libre con información clínica del paciente; la página debe tratarse como información sensible.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
