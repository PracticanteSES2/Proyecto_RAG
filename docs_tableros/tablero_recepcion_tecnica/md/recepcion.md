---
tablero: TABLERO RECEPCION TECNICA
pagina: RECEPCIÓN
nombre_funcional: Pedidos gestionados hoy en recepción técnica por estado
bloque: Día
tablas: []
actualizado: 2026-10-20
version: 1
---

# RECEPCIÓN

## Propósito
Muestra los pedidos de mercancía gestionados hoy en el proceso de Recepción Técnica: estado de cada registro, colaborador, observación, documentos de ingreso y tiempo de gestión, con el tiempo promedio por estado. Sirve para el control operativo del día (bloque Día). Se llega desde el botón RECEPCIÓN de CANTIDADES. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **Estados de pedidos del día**: Registros de estado (RTDetEstados) de los pedidos con fecha de hoy, unidos al nombre del estado, al colaborador y a los documentos de ingreso del pedido (REM para remisión, COMP para compra). Nombre de la tabla en el modelo por confirmar.

## Indicadores
- **Pedidos gestionados**: Pedidos con al menos un registro de estado hoy; probablemente conteo distinto de OidRTPedido. Por confirmar.
- **Tiempo promedio de gestión**: Promedio del tiempo que los pedidos permanecen en cada estado. Cálculo y unidad por confirmar (posiblemente minutos).

## Visuales
- **Filtros de la página**: Listas de COLABORADOR y ESTADO.
- **Tarjetas de indicadores**: PEDIDOS GESTIONADOS y TIEMPO PROMEDIO DE GESTIÓN.
- **Tabla de registros**: PEDIDO, ESTADO, OBSERVACIÓN, FECHA HORA REGISTRO, IngProd (documentos de ingreso), COLABORADOR y TIEMPO, ordenada por pedido de mayor a menor.
- **Circular por estado**: Titulado «TIEMPO PROMEDIO DE GESTIÓN por ESTADO»; reparto del tiempo promedio entre estados como Recepción Física, Verificación Registro Sanitario, Ingreso de Transportadora y Respuesta Novedad.
- **Botón inicio**: Regresa a CANTIDADES.

## Reglas de negocio
- **Solo hoy**: La consulta trae únicamente registros con fecha de registro igual a la fecha actual.
- **Colaborador**: Nombre y apellidos del usuario de la planilla que registró el estado.

## Observaciones
- **Cálculo de tiempo no documentado**: La consulta documentada no calcula el tiempo de gestión; la columna TIEMPO debe ser un cálculo en el modelo que no está documentado.
- **Sin PBIP de la página**: El PBIP disponible no trae los visuales de esta página; podría ser la página a la que lleva el botón DETALLE GESTION DIA de PROMEDIO GESTION MENSUAL.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
