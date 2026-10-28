---
tablero: TABLERO RECEPCION TECNICA
pagina: GENERAL
nombre_funcional: Seguimiento de solicitudes pendientes y de pedidos en recepción técnica
bloque: General
tablas: [PENDIENTES_RT, INGRESOS_DIA, TablaPedidosActuales, Tabla_Tiempos_Pedidos, PROMEDIO GESTION MENSUAL, PROMEDIO GESTION, CALENDARIO]
actualizado: 2026-10-28
version: 2
---

# GENERAL

## Propósito
Apoya el seguimiento operativo de Recepción Técnica. Tiene dos frentes: las solicitudes de productos pendientes de suministro de los dos últimos días (páginas CANTIDADES y DETALLE) y los pedidos que pasan por los estados del proceso de recepción (páginas INGRESOS DÍA y DETALLE RECEPCIÓN TECNICA, del día, y PROMEDIO GESTION MENSUAL, desde 2025). CANTIDADES es la página de inicio y la única visible; las demás se abren con botones.

## Fuentes de datos
- **PENDIENTES_RT**: Líneas de solicitudes de productos (CPNSOLICID) de los almacenes 51 y 62 con documento de los dos días anteriores y de hoy; trae producto, cantidades solicitada y pendiente, dependencia, área de servicio y horas desde la solicitud.
- **INGRESOS_DIA**: Registros de estado de pedidos de recepción técnica (RTDetEstados) con fecha de hoy: estado, observación, colaborador y documentos de ingreso (remisiones REM y compras COMP). Alimenta DETALLE RECEPCIÓN TECNICA.
- **TablaPedidosActuales**: Último registro de estado de cada pedido de INGRESOS_DIA (estado actual). Alimenta INGRESOS DÍA.
- **Tabla_Tiempos_Pedidos**: Fecha de cada etapa por pedido y minutos entre etapas (TIEMPO_1 a TIEMPO_5). Alimenta DETALLE RECEPCIÓN TECNICA.
- **PROMEDIO GESTION MENSUAL**: Días promedio por mes y estado desde el 1 de enero de 2025. Alimenta PROMEDIO GESTION MENSUAL.
- **PROMEDIO GESTION**: Registros de estado de los últimos 6 meses con la fecha del siguiente estado y el tiempo entre ambos en días; ninguna visual la usa.
- **CALENDARIO**: Tabla de fechas usada por el filtro de año de PROMEDIO GESTION MENSUAL.

## Definiciones
- **Tiempo de oportunidad**: Horas desde la fecha del documento de solicitud (CSCFECDOC) hasta el momento de la actualización de los datos. Columna PENDIENTES_RT[TIEMPO_DISPENSACION].
- **Horas de suministro**: Rango de horas de espera de la solicitud: 1. 0-6 horas, 2. 6-12 horas, 3. 12-18 horas, 4. 18-24 horas, 5. 24-48 horas (incluye 48) y 6. 48 o mas horas. Columna PENDIENTES_RT[HORAS_SUMINISTRO].
- **Área servicio**: Área que solicita el producto (GASNOMBRE).
- **Pedido**: Pedido de mercancía en el proceso de recepción técnica (OidRTPedido); pasa por estados como Ingreso de Transportadora, Recepción Física, Verificación Registro Sanitario, Recepción Técnica, Mercancía Almacenada, Novedad, Novedad en Trámite, Respuesta Novedad, Devuelto a Proveedor y Factura devuelta a Recepción Técnica.
- **Tiempo de gestión por estado**: Tiempo que un pedido permanece en un estado, desde su registro hasta el registro del estado siguiente del mismo pedido.

## Reglas de negocio
- **Almacenes incluidos**: Solo solicitudes de los almacenes con código interno 51 y 62.
- **Ventana de pendientes**: Solicitudes con fecha de documento entre hace dos días y hoy.
- **Ventana de pedidos**: INGRESOS DÍA y DETALLE RECEPCIÓN TECNICA muestran solo registros de hoy; PROMEDIO GESTION MENSUAL, los registros desde el 1 de enero de 2025 con un estado siguiente.

## Observaciones
- **Páginas del informe**: CANTIDADES, DETALLE, INGRESOS DÍA, DETALLE RECEPCIÓN TECNICA y PROMEDIO GESTION MENSUAL. La documentación original llama RECEPCIÓN a DETALLE RECEPCIÓN TECNICA y no describe INGRESOS DÍA.
- **Modo de las tablas**: PENDIENTES_RT, PROMEDIO GESTION y PROMEDIO GESTION MENSUAL están en DirectQuery; INGRESOS_DIA, CALENDARIO y las tablas calculadas, en importación.
- **Columna sin uso visible**: La documentación define TIEMPO_DESDE_SOLICITUD = DATEDIFF(PENDIENTES_RT[CSCFECDOC],TODAY(),HOUR), pero las tarjetas del PBIP usan TIEMPO_DISPENSACION calculada en SQL.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
