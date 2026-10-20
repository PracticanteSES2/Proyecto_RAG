---
tablero: TABLERO FINANCIERA
pagina: REFACTURACION X EPS
nombre_funcional: Devoluciones por aseguradora
bloque: Histórico
tablas: [REFACTURACION, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# REFACTURACION X EPS

## Propósito
Muestra las devoluciones por aseguradora (EPS) y por mes, con una torta de las devoluciones por servicio. Página oculta; se llega con el botón DEVOLUCIONES POR EPS de REFACTURACION, y su botón DEVOLUCIONES POR SERVICIO vuelve a REFACTURACION.

## Fuentes de datos
- **REFACTURACION**: Valor de devoluciones (VLRAREASERVICIO), aseguradora (TERCERO) y servicio (CLASIFICACION_SERVICIO).
- **CALENDARIO**: Jerarquía de año y mes.

## Indicadores
- **Devoluciones**: Suma de REFACTURACION[VLRAREASERVICIO], título DEVOLUCIONES. Unidad: pesos.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes con selección múltiple.
- **Segmentador aseguradora**: Lista desplegable ASEGURADORA (REFACTURACION[TERCERO]) con selección múltiple.
- **Botón devoluciones por servicio**: Botón DEVOLUCIONES POR SERVICIO que abre REFACTURACION.
- **Tabla devoluciones por aseguradora**: Matriz con ASEGURADORA (REFACTURACION[TERCERO]) en filas, meses en columnas y las DEVOLUCIONES.
- **Torta devoluciones por servicio**: Torta de DEVOLUCIONES por SERVICIO (REFACTURACION[CLASIFICACION_SERVICIO]) de mayor a menor, en millones.

## Reglas de negocio
- **Sin filtros fijos de fecha**: La página no filtra años; muestra todos salvo que se elijan en el segmentador.

## Observaciones
- **Columnas solo por mes**: La matriz no tiene el año en columnas; si se eligen varios años, cada mes suma todos los años.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
