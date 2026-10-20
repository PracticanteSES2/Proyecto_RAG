---
tablero: TABLERO FINANCIERA
pagina: FACTURACION PENDIENTE X EPS
nombre_funcional: Ingresos abiertos por aseguradora
bloque: Histórico
tablas: [FACTURACION_PENDIENTE, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# FACTURACION PENDIENTE X EPS

## Propósito
Muestra los ingresos abiertos (servicios todavía sin facturar) por aseguradora (EPS) y por mes, con una torta por servicio. Página oculta; se llega con el botón INGRESOS ABIERTOS POR EPS de FACTURACION PENDIENTE, y su botón INGRESOS ABIERTOS POR SERVICIO vuelve a esa página.

## Fuentes de datos
- **FACTURACION_PENDIENTE**: Valor de ingresos abiertos (VLSERVICIO), aseguradora (TERCERO) y servicio (CLASIFICACION_SERVICIO).
- **CALENDARIO**: Jerarquía de año y mes.

## Indicadores
- **Ingresos abiertos**: Suma de FACTURACION_PENDIENTE[VLSERVICIO], título INGRESOS ABIERTOS. Unidad: pesos.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes con selección múltiple.
- **Segmentador aseguradora**: Lista desplegable ASEGURADORA (FACTURACION_PENDIENTE[TERCERO]) con selección múltiple.
- **Botón ingresos abiertos por servicio**: Botón INGRESOS ABIERTOS POR SERVICIO que abre FACTURACION PENDIENTE.
- **Tabla ingresos abiertos por aseguradora**: Matriz con ASEGURADORA (FACTURACION_PENDIENTE[TERCERO]) en filas, meses en columnas y los INGRESOS ABIERTOS.
- **Torta ingresos abiertos por servicio**: Torta de INGRESOS ABIERTOS por SERVICIO (FACTURACION_PENDIENTE[CLASIFICACION_SERVICIO]) de mayor a menor, en millones.

## Reglas de negocio
- **Meses vacíos excluidos**: La matriz excluye los meses vacíos de la jerarquía de fechas.

## Observaciones
- **Columnas solo por mes**: La matriz no tiene el año en columnas; si se eligen varios años, cada mes suma todos los años.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
