---
tablero: TABLERO FINANCIERA
pagina: INGRESOS ABIERTOS ACTUAL
nombre_funcional: Consolidado de ingresos abiertos por asegurador y servicio
bloque: Histórico
tablas: [CONSOLIDADO_INGRESOS_ABIERTOS+, AREAS DE SERVICIO, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# INGRESOS ABIERTOS ACTUAL

## Propósito
Muestra el consolidado de ingresos abiertos (servicios todavía sin facturar) por asegurador y por servicio, mes a mes. Página oculta; se llega con el botón CONSOLIDADO INGRESOS ABIERTOS de INICIO.

## Fuentes de datos
- **CONSOLIDADO_INGRESOS_ABIERTOS+**: Asegurador (ASEGURADOR) y valor de ingresos abiertos (VLRSERVICIO).
- **AREAS DE SERVICIO**: Servicio (CLASIFICACION_SERVICIO) de la segunda matriz.
- **CALENDARIO**: Jerarquía de año y mes.

## Indicadores
- **Ingresos abiertos consolidados**: Suma de CONSOLIDADO_INGRESOS_ABIERTOS+[VLRSERVICIO], encabezado «Suma de VLRSERVICIO». Unidad: pesos.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes con selección múltiple.
- **Segmentador asegurador**: Lista desplegable ASEGURADOR (CONSOLIDADO_INGRESOS_ABIERTOS+[ASEGURADOR]).
- **Tabla por asegurador**: Matriz con ASEGURADOR en filas, año y mes en columnas y la suma de VLRSERVICIO.
- **Tabla por servicio**: Matriz con CLASIFICACION_SERVICIO (AREAS DE SERVICIO) en filas, año y mes en columnas y la suma de VLRSERVICIO.

## Reglas de negocio
- **Meses vacíos excluidos**: Las dos matrices excluyen los meses vacíos de la jerarquía de fechas.

## Observaciones
- **Encabezado técnico**: La columna de valor conserva el nombre automático «Suma de VLRSERVICIO».
- **Diferencia con FACTURACION PENDIENTE**: Por confirmar en qué se diferencia este consolidado de los ingresos abiertos de FACTURACION PENDIENTE y qué significa ACTUAL.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
