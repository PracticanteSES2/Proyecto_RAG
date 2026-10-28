---
tablero: TABLERO RECEPCION TECNICA
pagina: INGRESOS DÍA
nombre_funcional: Pedidos en gestión hoy y su estado actual
bloque: Día
tablas: [TablaPedidosActuales]
actualizado: 2026-10-28
version: 1
---

# INGRESOS DÍA

## Propósito
Muestra los pedidos de mercancía que hoy están en gestión en Recepción Técnica, cada uno en su estado actual (el último registrado), con el colaborador, la observación y los minutos que lleva en ese estado. Excluye los pedidos ya almacenados. Sirve para el control operativo del día (bloque Día). Es una página oculta: se llega desde el botón RECEPCIÓN de CANTIDADES y desde el botón ESTADO ACTUAL RECEPCIÓN de DETALLE RECEPCIÓN TECNICA.

## Fuentes de datos
- **TablaPedidosActuales**: Tabla calculada con el último registro de estado de cada pedido de INGRESOS_DIA (registros de hoy), con su columna TIEMPO en minutos.

## Indicadores
- **Pedidos en gestión**: Pedidos distintos con estado actual distinto de Mercancia Almacenada. DISTINCTCOUNT(TablaPedidosActuales[OidRTPedido]).
- **Tiempo promedio en gestión**: Minutos promedio que los pedidos llevan en su estado actual, desde su último registro hasta ahora. AVERAGE(TablaPedidosActuales[TIEMPO]).

## Visuales
- **Filtros de la página**: Listas de COLABORADOR (TablaPedidosActuales[USUARIO]) y ESTADO (TablaPedidosActuales[NomEstado]).
- **Tarjetas de indicadores**: PEDIDOS EN GESTIÓN y TIEMPO PROMEDIO EN GESTIÓN.
- **Tabla de pedidos**: PEDIDO, ESTADO, OBSERVACION, FECHA HORA REGISTRO, COLABORADOR y TIEMPO (minutos en el estado actual).
- **Circular por estado**: Pedidos por ESTADO actual.
- **Botones de navegación**: INICIO lleva a CANTIDADES; DETALLE GESTIÓN DÍA lleva a DETALLE RECEPCIÓN TECNICA.

## Reglas de negocio
- **Pedido en gestión**: La página filtra TablaPedidosActuales[NomEstado] distinto de «Mercancia Almacenada»; los pedidos almacenados salen del conteo.
- **Estado actual**: Es el registro con la fecha más reciente de cada pedido entre los registros de hoy.
- **Tiempo en gestión**: TablaPedidosActuales[TIEMPO] cuenta minutos desde el último registro hasta ahora (NOW), por lo que crece mientras el pedido no cambie de estado.

## Observaciones
- **Sin documentación original**: La documentación del propietario no describe esta página; se documenta a partir del informe y del modelo.
- **Solo registros de hoy**: Un pedido cuyo último estado se registró un día anterior no aparece.

## Historial de cambios
- **2026-10-28 · v1**: Diccionario y revisión contra el modelo y el informe.
