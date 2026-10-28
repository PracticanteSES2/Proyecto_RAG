---
tablero: TABLERO FINANCIERA
pagina: FACTURACIÓN GENERAL
nombre_funcional: Facturación, devoluciones y facturación neta por servicio (versión sin acceso desde INICIO)
bloque: Histórico
tablas: [FACTU_AREA, REFACTURACION, FACTURACION, AREAS DE SERVICIO, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# FACTURACIÓN GENERAL

## Propósito
Muestra por servicio y por mes la facturación, las devoluciones y la facturación neta, con una torta de la facturación por servicio. Página oculta: solo se llega con el botón FACTURACIÓN de COMPARATIVO, que tampoco tiene acceso desde INICIO. El botón FACTURACIÓN POR EPS lleva a FACTURACION X EPS.

## Fuentes de datos
- **FACTU_AREA**: Servicio (CLASIFICACION_SERVICIO) y valor facturado (TOTALAREASERVORDEN) de la matriz.
- **REFACTURACION**: Valor de devoluciones (VLRAREASERVICIO) de la matriz.
- **FACTURACION**: Valor facturado (TOTALAREASERVORDEN) de la torta.
- **AREAS DE SERVICIO**: Servicio (CLASIFICACION_SERVICIO) de la torta.
- **CALENDARIO**: Jerarquía de año y mes y medida NETA_AREA.

## Indicadores
- **Facturación por servicio**: Suma de FACTU_AREA[TOTALAREASERVORDEN], columna FACTURACION. Unidad: pesos.
- **Devoluciones**: Suma de REFACTURACION[VLRAREASERVICIO], columna DEVOLUCIONES. Unidad: pesos.
- **Facturación neta**: Medida CALENDARIO[NETA_AREA], columna FACTURACION NETA. Unidad: pesos. Cálculo: Por confirmar.
- **Facturación de la torta**: Suma de FACTURACION[TOTALAREASERVORDEN], título FACTURACIÓN. Unidad: pesos, etiquetas en millones.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes con selección múltiple; el de año no ofrece 2023.
- **Botón facturación por EPS**: Botón FACTURACIÓN POR EPS que abre FACTURACION X EPS.
- **Tabla facturación por servicio**: Matriz con SERVICIO (FACTU_AREA[CLASIFICACION_SERVICIO]) en filas, año y mes en columnas y los valores FACTURACION, DEVOLUCIONES y FACTURACION NETA.
- **Torta facturación por servicio**: Torta de FACTURACIÓN por SERVICIO (AREAS DE SERVICIO[CLASIFICACION_SERVICIO]) de mayor a menor, en millones.

## Reglas de negocio
- **Sin año 2023**: La matriz filtra año distinto de 2023 y el segmentador de año oculta 2023 y los años vacíos.
- **Servicio sin vacíos**: La matriz excluye los registros con FACTU_AREA[CLASIFICACION_SERVICIO] vacío.

## Observaciones
- **Página sin acceso desde INICIO**: Solo se abre desde COMPARATIVO; parece reemplazada por Duplicado de Duplicado de FACTURACIÓN GENERAL. Por confirmar si se debe eliminar.
- **Fuentes distintas en tabla y torta**: La matriz usa FACTU_AREA y la torta FACTURACION con AREAS DE SERVICIO; los totales pueden no coincidir. Por confirmar.
- **Copia casi idéntica**: Duplicado de FACTURACIÓN GENERAL repite esta página y solo cambia la tabla de la torta.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
