---
tablero: TABLERO FINANCIERA
pagina: COSTOS ANTERIOR
nombre_funcional: Venta, costo y rentabilidad por actividad y pagador (versión anterior)
bloque: Histórico
tablas: [COSTOS, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# COSTOS ANTERIOR

## Propósito
Versión anterior del análisis de costos: venta, costo, rentabilidad y frecuencia por actividad y pagador desde septiembre de 2024, calculados con columnas de la tabla COSTOS. Página oculta sin ningún botón que llegue a ella.

## Fuentes de datos
- **COSTOS**: Actividad (CUP_ACTIVIDAD), CENTROCOSTO, pagador (TERCERO), validacion y los valores VLRFACTURADO, VENTA, COSTO_TTL, COSTOACTIVIDAD, RENTABILIDAD, RENTABILIDAD_TOTAL, %RENT y CANTIDAD.
- **CALENDARIO**: Fecha del filtro de página y jerarquía de año y mes.

## Indicadores
- **Ventas**: Suma de COSTOS[VLRFACTURADO], tarjeta VENTAS. Unidad: pesos.
- **Costo**: Suma de COSTOS[COSTO_TTL], tarjeta COSTO. Unidad: pesos.
- **Rentabilidad total**: Suma de COSTOS[RENTABILIDAD_TOTAL], tarjeta RENTABILIDAD. Unidad: pesos.
- **Frecuencia**: Suma de COSTOS[CANTIDAD], tarjeta y columna FRECUENCIA. Unidad: cantidad de servicios.
- **Venta de la tabla**: Suma de COSTOS[VENTA], columna VENTA. Unidad: pesos.
- **Costo de la actividad**: Suma de COSTOS[COSTOACTIVIDAD], columna COSTO ACTIVIDAD. Unidad: pesos.
- **Rentabilidad de la tabla**: Suma de COSTOS[RENTABILIDAD], columna RENTABILIDAD. Unidad: pesos.
- **Porcentaje de rentabilidad**: Suma de COSTOS[%RENT], columna %RENTABILIDAD. Unidad: porcentaje.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes; el de año no ofrece 2023.
- **Segmentadores de CUPS, centro de costos y pagador**: Listas desplegables CUPS (COSTOS[CUP_ACTIVIDAD]), CENTRO DE COSTOS (COSTOS[CENTROCOSTO]) y PAGADOR (COSTOS[TERCERO]).
- **Segmentador validacion**: Lista validacion (COSTOS[validacion]).
- **Tarjetas de totales**: Cuatro tarjetas con el valor completo: VENTAS, COSTO, RENTABILIDAD y FRECUENCIA.
- **Tabla por actividad y pagador**: Matriz con ACTIVIDAD y PAGADOR en filas y FRECUENCIA, VENTA, COSTO ACTIVIDAD, RENTABILIDAD y %RENTABILIDAD, ordenada por frecuencia de mayor a menor.

## Reglas de negocio
- **Fecha de inicio de costos**: Filtro de página CALENDARIO[Date] mayor o igual al 1 de septiembre de 2024.
- **Centro de costos sin vacíos**: El segmentador de centro de costos excluye los valores vacíos.
- **Solo filas con frecuencia**: La matriz excluye las filas cuya frecuencia está vacía.
- **Barras de rentabilidad**: RENTABILIDAD y %RENTABILIDAD tienen barras de datos de -0,5 a 1: verde (#48F579) si es positiva y rojo (#F65B40) si es negativa.

## Observaciones
- **Página sin acceso**: Ningún botón lleva a esta página. Por confirmar si se debe eliminar.
- **Porcentaje sumado**: %RENTABILIDAD suma la columna %RENT; en filas con varios registros el porcentaje queda inflado. Por confirmar.
- **Segmentador validacion**: El significado y los valores de COSTOS[validacion] están por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
