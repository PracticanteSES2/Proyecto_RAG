---
tablero: TABLERO FINANCIERA
pagina: Duplicado de Duplicado de FACTURACIÓN GENERAL
nombre_funcional: Facturación, refacturación y facturación neta por servicio (página del botón FACTURACIÓN)
bloque: Histórico
tablas: [FACTURACION, FACTU_AREA, REFACTURACION, AREAS DE SERVICIO, AcreedoresConFactura, FiltroRefacturacion, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# Duplicado de Duplicado de FACTURACIÓN GENERAL

## Propósito
Página de facturación en uso: la abren el botón FACTURACIÓN de INICIO y el botón FACTURACIÓN POR SERVICIO de FACTURACION X EPS. Muestra por servicio y por mes la facturación, la refacturación según el modo elegido y la facturación neta, con filtros de asegurador y de modo, y una torta de la facturación por servicio. Página oculta; también recibe obtención de detalles (drillthrough) por tercero.

## Fuentes de datos
- **FACTURACION**: Valor facturado (TOTALAREASERVORDEN) de la matriz y tercero (OID_TERCERO) de la obtención de detalles.
- **FACTU_AREA**: Servicio y valor facturado de la torta.
- **REFACTURACION**: Columna NUEVOS_INGRESOS usada en el filtro del segmentador de modo.
- **AREAS DE SERVICIO**: Servicio (CLASIFICACION_SERVICIO) en las filas de la matriz.
- **AcreedoresConFactura**: Nombres de aseguradores del segmentador ASEGURADOR.
- **FiltroRefacturacion**: Columna Modo del segmentador que cambia el cálculo de la refacturación.
- **CALENDARIO**: Jerarquía de año y mes y medidas Refacturación Dinámica y Facturacion_net.

## Indicadores
- **Facturación**: Suma de FACTURACION[TOTALAREASERVORDEN], columna FACTURACIÓN. Unidad: pesos.
- **Refacturación dinámica**: Medida CALENDARIO[Refacturación Dinámica], columna REFACTURACIÓN; cambia según el valor elegido en FiltroRefacturacion[Modo]. Unidad: pesos. Cálculo: Por confirmar.
- **Facturación neta**: Medida CALENDARIO[Facturacion_net], columna FACTURACIÓN NETA. Unidad: pesos. Cálculo: Por confirmar.
- **Facturación de la torta**: Suma de FACTU_AREA[TOTALAREASERVORDEN], título FACTURACION. Unidad: pesos, etiquetas en millones.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes con selección múltiple; el de año no ofrece 2023.
- **Segmentador asegurador**: Lista desplegable ASEGURADOR (AcreedoresConFactura[nombre]) con selección múltiple.
- **Segmentador modo**: Lista desplegable Modo (FiltroRefacturacion[Modo]) de selección única; define qué devoluciones entran en REFACTURACIÓN.
- **Botón facturación por EPS**: Botón FACTURACIÓN POR EPS que abre FACTURACION X EPS.
- **Tabla facturación por servicio**: Matriz con CLASIFICACION_SERVICIO (AREAS DE SERVICIO) en filas, año y mes en columnas y los valores FACTURACIÓN, REFACTURACIÓN y FACTURACIÓN NETA.
- **Torta facturación por servicio**: Torta de FACTURACION por SERVICIO (FACTU_AREA[CLASIFICACION_SERVICIO]) de mayor a menor, en millones.

## Reglas de negocio
- **Sin año 2023**: La matriz filtra año distinto de 2023 y el segmentador de año oculta 2023 y los años vacíos.
- **Servicio sin vacíos**: La matriz excluye servicios vacíos tanto de FACTU_AREA como de AREAS DE SERVICIO.
- **Modo con nuevos ingresos**: El segmentador de modo tiene un filtro que excluye REFACTURACION[NUEVOS_INGRESOS] vacío.
- **Obtención de detalles por tercero**: La página recibe el filtro FACTURACION[OID_TERCERO] cuando se llega con obtener detalles desde otro visual.

## Observaciones
- **Nombre de copia**: El nombre indica que es una copia de FACTURACIÓN GENERAL, pero es la versión en uso. Por confirmar si se debe renombrar.
- **Valores de Modo**: Los valores de FiltroRefacturacion[Modo] y su efecto en la refacturación están por confirmar.
- **Fuentes distintas en tabla y torta**: La matriz usa FACTURACION con AREAS DE SERVICIO y la torta FACTU_AREA; los totales pueden no coincidir. Por confirmar.
- **Origen de la obtención de detalles**: Por confirmar desde qué visual se usa la obtención de detalles por tercero.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
