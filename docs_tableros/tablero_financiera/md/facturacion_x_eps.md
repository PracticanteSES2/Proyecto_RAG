---
tablero: TABLERO FINANCIERA
pagina: FACTURACION X EPS
nombre_funcional: Facturación, participación, devoluciones y facturación neta por asegurador
bloque: Histórico
tablas: [FACTURACION, REFACTURACION, AcreedoresConFactura, AREAS DE SERVICIO, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# FACTURACION X EPS

## Propósito
Muestra por asegurador (EPS) y por mes la facturación, su participación en el total del mes, las devoluciones y la facturación neta; abajo, una torta de la facturación por servicio. Página oculta; se llega con el botón FACTURACIÓN POR EPS de las páginas de facturación por servicio, y su botón FACTURACIÓN POR SERVICIO abre Duplicado de Duplicado de FACTURACIÓN GENERAL.

## Fuentes de datos
- **FACTURACION**: Valor facturado (TOTALAREASERVORDEN) de la matriz y de la torta.
- **REFACTURACION**: Valor de devoluciones (VLRAREASERVICIO).
- **AcreedoresConFactura**: Nombre del asegurador en filas y en el segmentador.
- **AREAS DE SERVICIO**: Servicio (CLASIFICACION_SERVICIO) de la torta.
- **CALENDARIO**: Jerarquía de año y mes y medida FACTURACION_NETA.

## Indicadores
- **Facturación**: Suma de FACTURACION[TOTALAREASERVORDEN], columna FACTURACIÓN. Unidad: pesos.
- **Participación en el mes**: Facturación del asegurador dividida por la facturación de todos los aseguradores en la misma columna de año y mes (cálculo del visual, % PARTICIPACIÓN). Unidad: porcentaje.
- **Devoluciones**: Suma de REFACTURACION[VLRAREASERVICIO], columna DEVOLUCIONES. Unidad: pesos.
- **Facturación neta**: Medida CALENDARIO[FACTURACION_NETA], columna FACTURACIÓN NETA. Unidad: pesos. Cálculo: Por confirmar.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes con selección múltiple.
- **Segmentador asegurador**: Lista desplegable ASEGURADOR (AcreedoresConFactura[nombre]) con selección múltiple.
- **Botón facturación por servicio**: Botón FACTURACIÓN POR SERVICIO que abre Duplicado de Duplicado de FACTURACIÓN GENERAL.
- **Tabla facturación por asegurador**: Matriz con ASEGURADOR (AcreedoresConFactura[nombre]) en filas, año y mes en columnas y los valores FACTURACIÓN, % PARTICIPACIÓN, DEVOLUCIONES y FACTURACIÓN NETA.
- **Torta facturación por servicio**: Torta de FACTURACIÓN por SERVICIO (AREAS DE SERVICIO[CLASIFICACION_SERVICIO]) de mayor a menor, en millones.

## Reglas de negocio
- **Sin año 2023**: La matriz filtra año distinto de 2023.

## Observaciones
- **Segmentador con 2023**: El segmentador de año sí ofrece 2023, pero la matriz lo excluye; al elegir solo 2023 la matriz queda vacía.
- **Torta sin asegurador en filas**: La torta es por servicio aunque la página es por asegurador; responde al segmentador de asegurador.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
