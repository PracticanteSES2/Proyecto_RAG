---
tablero: TABLERO FINANCIERA
pagina: REFACTURACION
nombre_funcional: Devoluciones por servicio
bloque: Histórico
tablas: [REFACTURACION, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# REFACTURACION

## Propósito
Muestra las devoluciones (facturas devueltas para refacturar) por servicio y por mes, con una torta del porcentaje de devoluciones de cada servicio. Página oculta; se llega con el botón DEVOLUCIONES de INICIO. El botón DEVOLUCIONES POR EPS lleva a REFACTURACION X EPS.

## Fuentes de datos
- **REFACTURACION**: Valor de devoluciones (VLRAREASERVICIO), servicio (CLASIFICACION_SERVICIO) y aseguradora (TERCERO).
- **CALENDARIO**: Jerarquía de año y mes.

## Indicadores
- **Devoluciones**: Suma de REFACTURACION[VLRAREASERVICIO], columna VALOR. Unidad: pesos.
- **Porcentaje de devoluciones por servicio**: Devoluciones del servicio divididas por el total de devoluciones del visual (cálculo del visual, título DEVOLUCIONES). Unidad: porcentaje.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes con selección múltiple.
- **Segmentador aseguradora**: Lista desplegable ASEGURADORA (REFACTURACION[TERCERO]) con selección múltiple.
- **Botón devoluciones por EPS**: Botón DEVOLUCIONES POR EPS que abre REFACTURACION X EPS.
- **Tabla devoluciones por servicio**: Matriz con SERVICIO (REFACTURACION[CLASIFICACION_SERVICIO]) en filas, meses en columnas y el VALOR de devoluciones.
- **Torta porcentaje por servicio**: Torta del porcentaje de DEVOLUCIONES por SERVICIO, de mayor a menor.

## Reglas de negocio
- **Sin filtros fijos de fecha**: La página no filtra años; muestra todos salvo que se elijan en el segmentador.

## Observaciones
- **Nombre de la página**: La página se llama REFACTURACION, pero el botón de INICIO y los títulos dicen DEVOLUCIONES.
- **Columnas solo por mes**: La matriz no tiene el año en columnas; si se eligen varios años, cada mes suma todos los años.
- **Etiquetas de la torta**: La torta muestra un porcentaje pero tiene configuradas unidades en millones. Por confirmar cómo se ve la etiqueta.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
