---
tablero: TABLERO RECEPCION TECNICA
pagina: PROMEDIO GESTION MENSUAL
nombre_funcional: Tiempo promedio mensual de gestión de pedidos por estado
bloque: Histórico
tablas: [CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# PROMEDIO GESTION MENSUAL

## Propósito
Muestra cómo evoluciona mes a mes el tiempo promedio que los pedidos de recepción técnica permanecen en cada estado, para detectar etapas lentas y cuellos de botella. Cubre los últimos 6 meses (bloque Histórico). Es una página oculta en la barra de páginas; tiene botón INICIO y un botón DETALLE GESTION DIA.

## Fuentes de datos
- **Estados de pedidos de seis meses**: Registros de estado (RTDetEstados) desde hace 6 meses, con la fecha del siguiente estado del mismo pedido (FECHA_FIN) y el tiempo entre ambos en días (TIEMPO_DIAS). Nombre de la tabla en el modelo por confirmar.
- **CALENDARIO**: Fechas para el filtro de año.

## Indicadores
- **Tiempo en estado**: Días que el pedido permanece en un estado, con decimales: minutos entre el registro del estado y el del estado siguiente divididos por 1440. Columna TIEMPO_DIAS.
- **Pedidos gestionados**: Total de pedidos o registros gestionados en el periodo; columna y agregación por confirmar.
- **Tiempo promedio en gestión**: Tiempo promedio de gestión del periodo; cálculo y unidad por confirmar.

## Visuales
- **Filtros de la página**: Año (CALENDARIO[Date]), Mes y ESTADO.
- **Tarjetas de indicadores**: PEDIDO GESTIONADOS y TIEMPO PROMEDIO EN GESTION.
- **Líneas por estado**: Titulado «DETALLE PROMEDIO GESTIÓN MENSUAL POR ESTADO»; un pequeño gráfico de líneas por estado (por ejemplo Devuelto a Proveedor, Factura devuelta a Recepción Técnica, Ingreso de Transportadora, Mercancía Almacenada, Novedad, Novedad en Trámite y Otro Estado) con el promedio mensual de días en el estado.
- **Botones de navegación**: INICIO regresa a CANTIDADES; DETALLE GESTION DIA abre otra página del informe (por confirmar si es RECEPCIÓN).

## Reglas de negocio
- **Orden de los estados**: El estado siguiente se busca por pedido, ordenando por fecha de registro y luego por el orden del estado.
- **Solo estados cerrados**: Se excluyen los registros sin estado siguiente (FECHA_FIN vacía), así que el último estado de cada pedido no cuenta.

## Observaciones
- **Escalas distintas**: La tarjeta de tiempo promedio muestra valores cercanos a 86 mientras las líneas por estado están entre 0 y 7 días; por confirmar la unidad o el cálculo de la tarjeta.
- **Pedidos gestionados alto**: La tarjeta muestra más de 250 000, lo que sugiere que cuenta registros de estado y no pedidos. Por confirmar.
- **Nombre en Power BI**: En el PBIP el nombre de la página termina con un espacio («PROMEDIO GESTION MENSUAL »).

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
