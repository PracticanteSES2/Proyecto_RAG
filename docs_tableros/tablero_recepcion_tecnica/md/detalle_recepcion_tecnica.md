---
tablero: TABLERO RECEPCION TECNICA
pagina: DETALLE RECEPCIÓN TECNICA
nombre_funcional: Detalle de la gestión de pedidos del día por estado y tiempos entre etapas
bloque: Día
tablas: [INGRESOS_DIA, Tabla_Tiempos_Pedidos]
actualizado: 2026-10-28
version: 2
---

# DETALLE RECEPCIÓN TECNICA

## Propósito
Muestra los registros de estado de los pedidos de mercancía gestionados hoy en Recepción Técnica: pedido, estado, fecha y hora, colaborador y minutos que el pedido estuvo en cada estado, con el tiempo promedio por estado y cinco tiempos promedio entre etapas del proceso. Sirve para el control operativo del día (bloque Día). Es una página oculta: se llega desde el botón DETALLE GESTIÓN DÍA de INGRESOS DÍA y desde el botón DETALLE GESTION DIA de PROMEDIO GESTION MENSUAL. La documentación del propietario la llama RECEPCIÓN.

## Fuentes de datos
- **INGRESOS_DIA**: Registros de estado (RTDetEstados) de los pedidos con fecha de hoy, unidos al nombre del estado y al colaborador; el modelo también trae la observación y los documentos de ingreso (REM para remisión, COMP para compra).
- **Tabla_Tiempos_Pedidos**: Tabla calculada con una fila por pedido de INGRESOS_DIA, con la fecha del último registro de cada etapa y los minutos entre etapas (TIEMPO_1 a TIEMPO_5).

## Indicadores
- **Pedidos gestionados**: Pedidos distintos con al menos un registro de estado hoy. DISTINCTCOUNT(INGRESOS_DIA[OidRTPedido]).
- **Tiempo promedio de gestión**: Minutos promedio que los pedidos permanecen en un estado. AVERAGE(INGRESOS_DIA[Dias_Hasta_Siguiente]).
- **Tiempo 1**: Minutos promedio entre el ingreso de la transportadora y la recepción física. AVERAGE(Tabla_Tiempos_Pedidos[TIEMPO_1]).
- **Tiempo 2**: Minutos promedio entre la recepción física y la recepción técnica. AVERAGE(Tabla_Tiempos_Pedidos[TIEMPO_2]).
- **Tiempo 3**: Minutos promedio entre la recepción técnica y la verificación del registro sanitario. AVERAGE(Tabla_Tiempos_Pedidos[TIEMPO_3]).
- **Tiempo 4**: Minutos promedio entre la verificación del registro sanitario y la recepción administrativa. AVERAGE(Tabla_Tiempos_Pedidos[TIEMPO_4]).
- **Tiempo 5**: Minutos promedio entre la recepción administrativa y el almacenamiento de la mercancía. AVERAGE(Tabla_Tiempos_Pedidos[TIEMPO_5]).

## Visuales
- **Filtros de la página**: Listas de COLABORADOR (INGRESOS_DIA[USUARIO]) y ESTADO (INGRESOS_DIA[NomEstado]).
- **Tarjetas de indicadores**: PEDIDOS GESTIONADOS y TIEMPO PROMEDIO GESTIÓN.
- **Tarjetas de tiempos entre etapas**: TIEMPO 1, TIEMPO 2, TIEMPO 3, TIEMPO 4 y TIEMPO 5.
- **Tabla de registros**: PEDIDO, ESTADO, FECHA HORA REGISTRO, COLABORADOR y TIEMPO GESTIÓN (suma de Dias_Hasta_Siguiente, en minutos).
- **Circular por estado**: Reparte por ESTADO el tiempo promedio de gestión (minutos).
- **Botones de navegación**: INICIO lleva a CANTIDADES; PROMEDIO GESTION MENSUAL lleva a esa página; ESTADO ACTUAL RECEPCIÓN lleva a INGRESOS DÍA.

## Reglas de negocio
- **Solo hoy**: La consulta trae únicamente registros con fecha de registro igual a la fecha actual.
- **Colaborador**: Nombre y apellidos del usuario de la planilla que registró el estado.
- **Tiempo en el estado**: INGRESOS_DIA[Dias_Hasta_Siguiente] mide minutos desde el registro hasta el registro siguiente del mismo pedido; en el último estado cuenta hasta ahora.
- **Tiempos entre etapas**: Cada tiempo usa la fecha del último registro de cada estado: Ingreso de Transportadora, Recepcion Fisica, Recepcion Tecnica, Verificacion Registro Sanitario, Recepcion Administrativa y Mercancia Almacenada.

## Observaciones
- **Nombre de la columna**: Dias_Hasta_Siguiente se llama «días» pero está en minutos.
- **Documentación antigua**: La documentación original (página RECEPCIÓN) muestra además OBSERVACIÓN y los documentos de ingreso en la tabla; en el informe actual esas columnas están en INGRESOS DÍA.
- **Tiempos entre etapas**: Solo hay valor cuando el pedido tiene registro hoy de las dos etapas; con registros fuera de orden pueden salir minutos negativos. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
