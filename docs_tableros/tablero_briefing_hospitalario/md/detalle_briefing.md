---
tablero: BRIEFING HOSPITALARIO
pagina: DETALLE BRIEFING
nombre_funcional: Casos abiertos reportados por las áreas para el briefing diario
bloque: Día
tablas: [BOLETIN]
actualizado: 2026-10-28
version: 2
---

# DETALLE BRIEFING

## Propósito
Lista los casos y novedades que las áreas del hospital reportan para el briefing diario (por ejemplo incapacidades, pedidos demorados, equipos dañados), con la descripción, el último seguimiento, el colaborador que lo hizo y su fecha. Sirve para dar trazabilidad a cada requerimiento. Se llega desde el botón DETALLE BRIEFING del visual CASOS por SERVICIO en INICIO.

## Fuentes de datos
- **BOLETIN**: Solicitudes de servicio (DNSOLISERVICIO_NEW) de la categoría 366 en estados 1, 2 o 3, con el área que reporta (GENDEPEND), la descripción, fechas de creación y cierre, y el último seguimiento en estado 3 (fecha, observación y usuario).

## Indicadores
- **Casos totales**: Casos del briefing abiertos. DISTINCTCOUNT(BOLETIN[OID_SOLICITUD]).
- **Tiempo de trámite**: Horas entre el último seguimiento (o la creación si no hay) y el cierre (o ahora si sigue abierto). Columna TIEMPO_TRAMITE.
- **Tiempo para seguimiento**: Horas entre la creación del caso y el seguimiento (o ahora si no hay). Columna TIEMPO_PARA_PRIMER_SEGUIMIENTO.

## Visuales
- **Tarjeta CASOS TOTALES**: Total según el filtro de servicio.
- **Segmentador SERVICIO**: Área que reporta el caso.
- **Tabla de casos**: SERVICIO, DESCRIPCIÓN SOLICITUD, ÚLTIMO SEGUIMIENTO, COLABORADOR ÚLTIMO SEGUIMIENTO y FECHA ÚLTIMO SEGUIMIENTO.

## Reglas de negocio
- **Categoría del briefing**: Solo solicitudes de la categoría de servicio 366.
- **Casos abiertos**: Solo solicitudes con EstadoOid 1, 2 o 3.
- **Seguimiento mostrado**: Se toma el registro de historial en estado 3 más reciente; si no hay, la fecha de seguimiento es la de creación.
- **Nombre del colaborador**: NOM_COMPLETO une NOMBRE_USUARIO y APELLIDOS_USUARIO.

## Observaciones
- **Primer o último seguimiento**: La consulta llama PRIMER_SEGUIMIENTO al registro, pero lo ordena por fecha descendente, así que trae el último; la tabla lo titula correctamente ÚLTIMO SEGUIMIENTO.
- **Significado de estados**: Qué representan los estados 1, 2 y 3 de la solicitud y el estado 3 del historial está por confirmar.
- **Nombre de página**: La página se llama DETALLE BRIEFING en Power BI; está oculta y se llega con el botón DETALLE de su visual en INICIO.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
