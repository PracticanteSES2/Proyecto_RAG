---
tablero: BRIEFING HOSPITALARIO
pagina: DETALLE MEDICAMENTOS DESABASTECIDOS
nombre_funcional: Casos abiertos de medicamentos e insumos desabastecidos
bloque: Día
tablas: [MEDICAMENTOS DESABASTECIDOS]
actualizado: 2026-10-20
version: 1
---

# DETALLE MEDICAMENTOS DESABASTECIDOS

## Propósito
Lista los medicamentos e insumos que las áreas reportan como desabastecidos y siguen abiertos, con el servicio que reporta, la descripción, el último seguimiento, quién lo hizo y las fechas. Sirve para controlar la gestión del abastecimiento. Se llega desde el botón DETALLE de la tarjeta MEDICAMENTOS E INSUMOS DESABASTECIDOS en INICIO.

## Fuentes de datos
- **MEDICAMENTOS DESABASTECIDOS**: Solicitudes de servicio (DNSOLISERVICIO_NEW) de la categoría 325 en estados 1, 2 o 3, con el área que reporta, la descripción, fechas de creación y cierre, y el último seguimiento en estado 3 (fecha, observación y usuario).

## Indicadores
- **Casos totales**: Casos de desabastecimiento abiertos. DISTINCTCOUNT(MEDICAMENTOS DESABASTECIDOS[OID_SOLICITUD]).

## Visuales
- **Tarjeta CASOS TOTALES**: Total de casos abiertos; en INICIO se muestra como MEDICAMENTOS E INSUMOS DESABASTECIDOS.
- **Tabla de casos**: SERVICIO, DESCRIPCIÓN, ÚLTIMO SEGUIMIENTO, USUARIO ÚLTIMO SEGUIMIENTO, FECHA DE CREACIÓN y FECHA ÚLTIMO SEGUIMIENTO.

## Reglas de negocio
- **Categoría de desabastecimiento**: Solo solicitudes de la categoría de servicio 325.
- **Casos abiertos**: Solo solicitudes con EstadoOid 1, 2 o 3.
- **Seguimiento mostrado**: Registro de historial en estado 3 más reciente de cada caso.
- **Nombre del usuario**: NOM_COMPLETO_MD une NOMBRE_USUARIO y APELLIDOS_USUARIO.

## Observaciones
- **Primer o último seguimiento**: Igual que en DETALLE BRIEFING, la consulta llama PRIMER_SEGUIMIENTO al registro más reciente.
- **Fecha de seguimiento vacía**: A diferencia de DETALLE BRIEFING, aquí la fecha de seguimiento queda vacía si el caso no tiene seguimiento.
- **Misma fuente en TABLERO CVC**: El tablero CVC usa la misma categoría 325 para marcar productos desabastecidos.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
