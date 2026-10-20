---
tablero: TABLERO FINANCIERA
pagina: Duplicado de FACTURACIÓN GENERAL
nombre_funcional: Facturación, devoluciones y facturación neta por servicio (copia sin acceso)
bloque: Histórico
tablas: [FACTU_AREA, REFACTURACION, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# Duplicado de FACTURACIÓN GENERAL

## Propósito
Copia de FACTURACIÓN GENERAL: facturación, devoluciones y facturación neta por servicio y por mes, con una torta de la facturación por servicio. Página oculta sin ningún botón que llegue a ella; su botón FACTURACIÓN POR EPS lleva a FACTURACION X EPS.

## Fuentes de datos
- **FACTU_AREA**: Servicio (CLASIFICACION_SERVICIO) y valor facturado (TOTALAREASERVORDEN) de la matriz y de la torta.
- **REFACTURACION**: Valor de devoluciones (VLRAREASERVICIO).
- **CALENDARIO**: Jerarquía de año y mes y medida NETA_AREA.

## Indicadores
- **Facturación por servicio**: Suma de FACTU_AREA[TOTALAREASERVORDEN], columna FACTURACION y torta. Unidad: pesos.
- **Devoluciones**: Suma de REFACTURACION[VLRAREASERVICIO], columna DEVOLUCIONES. Unidad: pesos.
- **Facturación neta**: Medida CALENDARIO[NETA_AREA], columna FACTURACION NETA. Unidad: pesos. Cálculo: Por confirmar.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes con selección múltiple; el de año no ofrece 2023.
- **Botón facturación por EPS**: Botón FACTURACIÓN POR EPS que abre FACTURACION X EPS.
- **Tabla facturación por servicio**: Matriz con SERVICIO (FACTU_AREA[CLASIFICACION_SERVICIO]) en filas, año y mes en columnas y FACTURACION, DEVOLUCIONES y FACTURACION NETA.
- **Torta facturación por servicio**: Torta de FACTURACION por SERVICIO (FACTU_AREA[CLASIFICACION_SERVICIO]) de mayor a menor, en millones.

## Reglas de negocio
- **Sin año 2023**: La matriz filtra año distinto de 2023 y el segmentador de año oculta 2023 y los años vacíos.
- **Servicio sin vacíos**: La matriz excluye los registros con FACTU_AREA[CLASIFICACION_SERVICIO] vacío.

## Observaciones
- **Página sin acceso**: Ningún botón lleva a esta página. Por confirmar si se debe eliminar.
- **Diferencia con FACTURACIÓN GENERAL**: Solo cambia la torta, que aquí usa FACTU_AREA en lugar de FACTURACION con AREAS DE SERVICIO.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
