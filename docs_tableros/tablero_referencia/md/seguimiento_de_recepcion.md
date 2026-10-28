---
tablero: TABLERO REFERENCIA
pagina: SEGUIMIENTO DE RECEPCION
nombre_funcional: Bitácora de seguimiento de las solicitudes recibidas
bloque: Día
tablas: [REFERENCIA]
actualizado: 2026-10-20
version: 1
---

# SEGUIMIENTO DE RECEPCION

## Propósito
Muestra la bitácora de cada solicitud de referencia recibida: las anotaciones de seguimiento (llamadas, validaciones clínicas, trámites administrativos, autorizaciones, ingreso) por paciente. Sirve para dar trazabilidad a los casos. Seguimiento reciente (bloque Día); se llega desde el botón SEGUIMIENTO RECEPCIÓN de las páginas de detalle. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **REFERENCIA**: Solicitudes de recepción de los últimos 30 días. La tabla de anotaciones (columna Descripcion) no tiene consulta documentada; probablemente viene de SEG_RECEPCIONES. Por confirmar.

## Indicadores
- **Cantidad de solicitudes**: Número de solicitudes en el filtro. Medida exacta por confirmar.
- **Tiempo promedio de respuesta**: Promedio en horas de REFERENCIA[TIEMPO_REMISION]. Agregación por confirmar.
- **Promedio de edad**: Promedio en años de REFERENCIA[ANOS]. Agregación por confirmar.

## Visuales
- **Tarjetas**: CANTIDAD DE SOLICITUDES, TIEMPO PROMEDIO RESPUESTA y PROMEDIO DE EDAD.
- **Filtros**: Segmentadores de EPS y DOCUMENTO y control de rango de fechas.
- **Tabla de pacientes y descripciones**: Columnas IDENTIFICACIÓN, NOMBRE y Descripcion; una fila por anotación de seguimiento, por lo que un paciente puede tener varias filas.
- **Botones de navegación**: NO ACEPTADOS RECEPCIÓN y ACEPTADOS RECEPCIÓN; el botón de inicio vuelve a INICIO.

## Observaciones
- **Filtros documentados**: La documentación dice que los filtros son EPS, rango de edad y fechas, pero la captura muestra EPS, DOCUMENTO y fechas. Por confirmar.
- **Texto libre clínico**: Las descripciones son texto libre con información clínica del paciente; la página debe tratarse como información sensible.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
