---
tablero: TABLERO FINANCIERA
pagina: FACTURACION PENDIENTE
nombre_funcional: Ingresos abiertos por servicio
bloque: Histórico
tablas: [FACTURACION_PENDIENTE, FACTURACION, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# FACTURACION PENDIENTE

## Propósito
Muestra los ingresos abiertos (servicios todavía sin facturar) por servicio y por mes, con una torta por servicio. Página oculta; se llega con el botón INGRESOS ABIERTOS de INICIO. El botón INGRESOS ABIERTOS POR EPS lleva a FACTURACION PENDIENTE X EPS.

## Fuentes de datos
- **FACTURACION_PENDIENTE**: Valor de ingresos abiertos (VLSERVICIO), servicio (CLASIFICACION_SERVICIO) y aseguradora (TERCERO).
- **FACTURACION**: Tercero (NOMBRETERCERO) y valor a cargo de la entidad (VLRENTIDADORDEN) del filtro Top N de la torta.
- **CALENDARIO**: Jerarquía de año y mes.

## Indicadores
- **Ingresos abiertos**: Suma de FACTURACION_PENDIENTE[VLSERVICIO], título INGRESOS ABIERTOS. Unidad: pesos.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes con selección múltiple.
- **Segmentador aseguradora**: Lista desplegable ASEGURADORA (FACTURACION_PENDIENTE[TERCERO]) con selección múltiple.
- **Botón ingresos abiertos por EPS**: Botón INGRESOS ABIERTOS POR EPS que abre FACTURACION PENDIENTE X EPS.
- **Tabla ingresos abiertos por servicio**: Matriz con SERVICIO (FACTURACION_PENDIENTE[CLASIFICACION_SERVICIO]) en filas, meses en columnas y los INGRESOS ABIERTOS.
- **Torta ingresos abiertos por servicio**: Torta de INGRESOS ABIERTOS por SERVICIO de mayor a menor, en millones.

## Reglas de negocio
- **Top 5 en la torta**: La torta tiene un filtro Top N que deja los 5 FACTURACION[NOMBRETERCERO] con mayor suma de FACTURACION[VLRENTIDADORDEN].
- **Meses vacíos excluidos**: La matriz excluye los meses vacíos de la jerarquía de fechas.

## Observaciones
- **Top 5 de otra tabla**: El filtro Top N de la torta usa terceros de FACTURACION y no de FACTURACION_PENDIENTE; por confirmar si limita de verdad la torta a cinco aseguradores.
- **Columnas solo por mes**: La matriz no tiene el año en columnas; si se eligen varios años, cada mes suma todos los años.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
