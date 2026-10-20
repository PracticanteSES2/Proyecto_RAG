---
tablero: TABLERO FINANCIERA
pagina: CUPS
nombre_funcional: Frecuencia y valor por CUPS, asegurador y servicio
bloque: Histórico
tablas: [CUPS, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# CUPS

## Propósito
Muestra la frecuencia y el valor de los servicios por código CUPS, mes a mes, con su participación en el total del mes, y tortas del valor por aseguradora y por servicio. Página oculta; se llega con el botón CUPS de INICIO.

## Fuentes de datos
- **CUPS**: Código CUPS (SERVIPSPRODUCTO), CANTIDAD, valor VLRTOTSERV, aseguradora (NOMBRE_TERCERO), CENTROCOSTO, servicio (CLASIFICACION_SERVICIO) e INCLUIRPRODUCTOS.
- **CALENDARIO**: Jerarquía de año y mes.

## Indicadores
- **Frecuencia**: Suma de CUPS[CANTIDAD], columna FRECUENCIA. Unidad: cantidad de servicios.
- **Porcentaje de frecuencia**: Frecuencia del CUPS dividida por la frecuencia total de la misma columna de año y mes (cálculo del visual, %TOTAL FRECUENCIA). Unidad: porcentaje.
- **Valor total**: Suma de CUPS[VLRTOTSERV], columna TOTAL. Unidad: pesos.
- **Participación en valor**: Valor del CUPS dividido por el valor total de la misma columna de año y mes (cálculo del visual, %PARTICIPACION). Unidad: porcentaje.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes con selección múltiple.
- **Segmentador asegurador**: Lista desplegable ASEGURADOR (CUPS[NOMBRE_TERCERO]).
- **Segmentador centro de costo**: Lista desplegable CENTROCOSTO (CUPS[CENTROCOSTO]).
- **Segmentador mostrar medicamentos**: Lista MOSTRAR MEDICAMENTOS (CUPS[INCLUIRPRODUCTOS]) para incluir o no los productos.
- **Segmentador CUPS**: Lista desplegable CUPS (CUPS[SERVIPSPRODUCTO]).
- **Tabla CUPS por mes**: Matriz con SERVIPSPRODUCTO en filas, año y mes en columnas y FRECUENCIA, %TOTAL FRECUENCIA, TOTAL y %PARTICIPACION, ordenada por frecuencia de mayor a menor.
- **Torta por aseguradora**: Torta del TOTAL por ASEGURADORA (CUPS[NOMBRE_TERCERO]) con el valor completo.
- **Torta por servicio**: Torta del TOTAL por SERVICIO (CUPS[CLASIFICACION_SERVICIO]) con el valor completo.

## Reglas de negocio
- **Interacción tabla y tortas**: Seleccionar un CUPS en la matriz filtra las dos tortas, y cada torta filtra a la otra.
- **Meses vacíos excluidos**: La matriz y las tortas excluyen los meses vacíos de la jerarquía de fechas.

## Observaciones
- **Valores de mostrar medicamentos**: Los valores de INCLUIRPRODUCTOS y si por defecto se incluyen medicamentos están por confirmar.
- **Columna de medicamentos repetida**: El segmentador usa INCLUIRPRODUCTOS y tiene un filtro sobre INCLUIRPRODUC; por confirmar si son la misma columna.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
