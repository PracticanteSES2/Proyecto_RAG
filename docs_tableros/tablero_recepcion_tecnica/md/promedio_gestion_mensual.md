---
tablero: TABLERO RECEPCION TECNICA
pagina: PROMEDIO GESTION MENSUAL
nombre_funcional: Tiempo promedio mensual de gestión de pedidos por estado
bloque: Histórico
tablas: [PROMEDIO GESTION MENSUAL, CALENDARIO]
actualizado: 2026-10-28
version: 2
---

# PROMEDIO GESTION MENSUAL

## Propósito
Muestra cómo evoluciona mes a mes el tiempo promedio que los pedidos de recepción técnica permanecen en cada estado, para detectar etapas lentas y cuellos de botella. Cubre desde el 1 de enero de 2025 (bloque Histórico). Es una página oculta; en Power BI su nombre termina con un espacio. Se llega desde el botón PROMEDIO GESTION MENSUAL de DETALLE RECEPCIÓN TECNICA y tiene un botón DETALLE GESTION DIA de regreso a esa página.

## Fuentes de datos
- **PROMEDIO GESTION MENSUAL**: Una fila por mes (PERIODO) y estado, con CANTIDAD_REGISTROS y PROMEDIO_TIEMPO_GESTION_DIAS, calculada en SQL desde RTDetEstados con registros desde el 1 de enero de 2025 y solo estados con estado siguiente.
- **PROMEDIO GESTION**: Registros de estado de los últimos 6 meses con FECHA_FIN y TIEMPO_DIAS; está en el modelo pero ninguna visual la usa.
- **CALENDARIO**: Fechas para el filtro de año.

## Indicadores
- **Tiempo en estado**: Días que los pedidos permanecen en un estado en el mes: promedio de los días calendario entre el registro del estado y el del siguiente (PROMEDIO GESTION MENSUAL[PROMEDIO_TIEMPO_GESTION_DIAS]). En PROMEDIO GESTION, TIEMPO_DIAS lo da con decimales (minutos divididos entre 1440).
- **Pedidos gestionados**: Suma de PROMEDIO GESTION MENSUAL[CANTIDAD_REGISTROS], que cuenta estados terminados del periodo y no pedidos distintos.
- **Tiempo promedio en gestión**: Suma de PROMEDIO_TIEMPO_GESTION_DIAS en días de los meses y estados filtrados; al sumar promedios no es un promedio real.

## Visuales
- **Filtros de la página**: Segmentación de CALENDARIO[Date] (Año), de CALENDARIO[Date] (Mes) y de PROMEDIO GESTION MENSUAL[NomEstado] (ESTADO).
- **Tarjetas de indicadores**: PEDIDO GESTIONADOS y TIEMPO PROMEDIO EN GESTION.
- **Líneas por estado**: Titulado «DETALLE PROMEDIO GESTIÓN MENSUAL POR ESTADO»; un pequeño gráfico de líneas por estado (por ejemplo Devuelto a Proveedor, Factura devuelta a Recepción Técnica, Ingreso de Transportadora, Mercancía Almacenada, Novedad, Novedad en Trámite y Otro Estado) con el promedio mensual de días en el estado.
- **Botón de navegación**: DETALLE GESTION DIA lleva a DETALLE RECEPCIÓN TECNICA.

## Reglas de negocio
- **Orden de los estados**: El estado siguiente se busca por pedido, ordenando por fecha de registro y luego por el orden del estado.
- **Solo estados cerrados**: Se excluyen los registros sin estado siguiente, así que el último estado de cada pedido no cuenta.
- **Mes del estado**: El periodo es el mes en que termina el estado (fecha del estado siguiente) y los días se cuentan como días calendario.

## Observaciones
- **Escalas distintas**: La tarjeta de tiempo promedio muestra valores cercanos a 86 mientras las líneas por estado están entre 0 y 7 días, porque la tarjeta suma los promedios de todos los meses y estados. Por confirmar si debe promediarse.
- **Pedidos gestionados alto**: La tarjeta muestra más de 250 000 porque cuenta registros de estado y no pedidos distintos.
- **Calendario corto**: CALENDARIO empieza el 1 de septiembre de 2025, por lo que los meses anteriores no aparecen en los filtros de año y mes ni en el gráfico.
- **Documentación antigua**: La documentación original describe una consulta de 6 meses con TIEMPO_DIAS decimal; el modelo actual agrega por mes desde 2025.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
