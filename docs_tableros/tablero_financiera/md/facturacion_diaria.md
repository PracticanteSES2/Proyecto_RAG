---
tablero: TABLERO FINANCIERA
pagina: FACTURACION DIARIA
nombre_funcional: Facturación e ingresos abiertos del mes en curso por pagador y centro de costos
bloque: Día
tablas: [FACTURACION_DIARIA, INGRESOS_AB_DIARIO, TERCEROS, AREAS DE SERVICIO, CALENDARIO]
actualizado: 2026-11-03
version: 3
---

# FACTURACION DIARIA

## Propósito
Muestra la facturación y los ingresos abiertos del mes en curso por pagador y por centro de costos, con tortas del porcentaje facturado. Se puede acotar a un rango de días, a facturas de copago y a lo recaudado por franquicia. Página oculta; se llega con el botón FACTURACIÓN DIARIA de INICIO.

## Fuentes de datos
- **FACTURACION_DIARIA**: Valor facturado (TOTALAREASERV), centro de costos (SERVICIO_R), aseguradora (NOMBRETERCERO) y marcas FACTUCOPAGO y RECAUDADO_FRANQUICIA.
- **INGRESOS_AB_DIARIO**: Valor de ingresos abiertos (VLRSERVICIO).
- **TERCEROS**: Nombre comercial del pagador (TERNOMCOM).
- **AREAS DE SERVICIO**: Centro de costos (CLASIFICACION_SERVICIO) de la matriz.
- **CALENDARIO**: Fecha del filtro de mes en curso y del segmentador de rango.

## Indicadores
- **Total facturado**: Suma de FACTURACION_DIARIA[TOTALAREASERV], columna TOTAL FACTURADO. Unidad: pesos.
- **Ingresos abiertos**: Suma de INGRESOS_AB_DIARIO[VLRSERVICIO], columna INGRESOS ABIERTOS. Unidad: pesos.
- **Porcentaje facturado**: TOTALAREASERV de cada categoría dividido por el total del visual (cálculo del visual, PORCENTAJE FACTURADO). Unidad: porcentaje.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentador asegurador**: Lista desplegable ASEGURADOR (TERCEROS[TERNOMCOM]) con selección múltiple.
- **Segmentador de fechas**: Control de rango entre dos fechas sobre CALENDARIO[Date].
- **Segmentador factura de copago**: Lista FACTURA DE COPAGO (FACTURACION_DIARIA[FACTUCOPAGO]).
- **Segmentador recaudado por franquicia**: Lista RECAUDADO POR FRANQUICIA (FACTURACION_DIARIA[RECAUDADO_FRANQUICIA]).
- **Tabla por pagador**: Matriz con PAGADOR (TERCEROS[TERNOMCOM]) en filas y TOTAL FACTURADO e INGRESOS ABIERTOS, ordenada por ingresos abiertos de mayor a menor.
- **Tabla por centro de costos**: Matriz con CENTRO COSTOS (AREAS DE SERVICIO[CLASIFICACION_SERVICIO]) en filas y TOTAL FACTURADO e INGRESOS ABIERTOS, ordenada por total facturado de mayor a menor.
- **Torta por centro de costos**: Torta del PORCENTAJE FACTURADO por CENTRO COSTOS (FACTURACION_DIARIA[SERVICIO_R]).
- **Torta por aseguradora**: Torta del PORCENTAJE FACTURADO por ASEGURADORA (FACTURACION_DIARIA[NOMBRETERCERO]).

## Reglas de negocio
- **Mes en curso**: Filtro de página de fecha relativa: CALENDARIO[Date] dentro del mes calendario actual.
- **Interacción tablas y tortas**: Seleccionar una fila de cualquiera de las dos matrices filtra las dos tortas.
- **Meses vacíos excluidos**: Las dos matrices excluyen los meses vacíos de la jerarquía de fechas.

## Observaciones
- **Diaria con datos del mes**: Pese al nombre, la página muestra todo el mes en curso; para ver un día hay que acotar el segmentador de fechas.
- **Centro de costos de dos fuentes**: La matriz agrupa por AREAS DE SERVICIO[CLASIFICACION_SERVICIO] y la torta por FACTURACION_DIARIA[SERVICIO_R], que es el nombre del centro de costos (NOMCENCOST) o «FACTURA COPAGO POR FRANQUICIA» si la factura no tiene área y es de copago. Son clasificaciones distintas, así que los nombres no tienen por qué coincidir.
- **Valores de copago y franquicia**: FACTUCOPAGO vale «SI» o «NO». RECAUDADO_FRANQUICIA vale «SI» cuando SERVICIO_R es «FACTURA COPAGO POR FRANQUICIA» y «NO» en los demás casos.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
- **2026-11-03 · v2**: Se completó con el modelo sincronizado del Power BI (2026-10-29): valores de RECAUDADO_FRANQUICIA y origen de SERVICIO_R. Autor: agente dic-pendientes.
- **2026-11-03 · v3**: Resultados de las consultas financiera-01 a financiera-07 contra el modelo publicado (2026-11-03) Autor: agente dic-pendientes.
