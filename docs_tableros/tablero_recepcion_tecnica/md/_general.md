---
tablero: TABLERO RECEPCION TECNICA
pagina: GENERAL
nombre_funcional: Seguimiento de solicitudes pendientes y de pedidos en recepción técnica
bloque: General
tablas: [PENDIENTES_RT, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# GENERAL

## Propósito
Apoya el seguimiento operativo de Recepción Técnica. Tiene dos frentes: las solicitudes de productos pendientes de suministro de los dos últimos días (páginas CANTIDADES y DETALLE) y los pedidos que pasan por los estados del proceso de recepción (páginas RECEPCIÓN, del día, y PROMEDIO GESTION MENSUAL, de los últimos seis meses). CANTIDADES es la página de inicio.

## Fuentes de datos
- **PENDIENTES_RT**: Líneas de solicitudes de productos (CPNSOLICID) de los almacenes 51 y 62 con documento de los dos días anteriores y de hoy; trae producto, cantidades solicitada y pendiente, dependencia, área de servicio y horas desde la solicitud.
- **Estados de pedidos del día**: Registros de estado de pedidos de recepción técnica (RTDetEstados) con fecha de hoy: estado, observación, colaborador y documentos de ingreso (remisiones REM y compras COMP). Nombre de la tabla en el modelo por confirmar.
- **Estados de pedidos de seis meses**: Registros de estado de los últimos 6 meses con la fecha del siguiente estado del mismo pedido y el tiempo entre ambos en días. Nombre de la tabla en el modelo por confirmar.
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
- **Ventana de pedidos**: RECEPCIÓN muestra solo registros de hoy; PROMEDIO GESTION MENSUAL, los de los últimos 6 meses con un estado siguiente.

## Observaciones
- **PBIP incompleto**: El PBIP lista cinco páginas pero solo trae la definición de CANTIDADES y de parte de PROMEDIO GESTION MENSUAL, sin modelo semántico; lo demás se describe con la documentación y sus capturas. Una de las cinco páginas no está en la documentación.
- **Modo de las tablas**: El catálogo local indica modo import; por confirmar con el modelo.
- **Columna sin uso visible**: La documentación define TIEMPO_DESDE_SOLICITUD = DATEDIFF(PENDIENTES_RT[CSCFECDOC],TODAY(),HOUR), pero las tarjetas del PBIP usan TIEMPO_DISPENSACION calculada en SQL.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
