---
tablero: TABLERO FINANCIERA
pagina: COSTOS X MESES
nombre_funcional: Costo por actividad mes a mes y utilidad de las principales entidades
bloque: Histórico
tablas: [COSTOS, CUPS, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# COSTOS X MESES

## Propósito
Muestra el costo promedio y la frecuencia por actividad (CUPS) mes a mes desde septiembre de 2024, y la facturación con el porcentaje de utilidad de las 10 entidades que más facturan. Página oculta sin ningún botón que llegue a ella; su botón de inicio vuelve a INICIO.

## Fuentes de datos
- **COSTOS**: Actividad (CUP_ACTIVIDAD, NOMBREACTIVIDAD), CUPS y costo de la actividad (COSTOACTIVIDAD).
- **CUPS**: Frecuencia (CANTIDAD), valor facturado (VLRTOTSERV) y entidad (NOMBRE_TERCERO).
- **CALENDARIO**: Fecha del filtro de página, jerarquía de año y mes y medida %UTILIDAD.

## Indicadores
- **Costo de la actividad**: Promedio de COSTOS[COSTOACTIVIDAD], columna COSTO ACTIVIDAD. Unidad: pesos.
- **Frecuencia**: Suma de CUPS[CANTIDAD], columna FRECUENCIA. Unidad: cantidad de servicios.
- **Facturación por entidad**: Suma de CUPS[VLRTOTSERV], título FACTURACIÓN. Unidad: pesos.
- **Porcentaje de utilidad**: Medida CALENDARIO[%UTILIDAD]. Unidad: porcentaje. Cálculo: Por confirmar.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes; el de año no ofrece 2023.
- **Segmentador CUPS**: Lista desplegable CUPS (COSTOS[CUPS]).
- **Segmentador actividad**: Lista desplegable ACTIVIDAD (COSTOS[NOMBREACTIVIDAD]).
- **Tabla costo por actividad**: Matriz con ACTIVIDAD (COSTOS[CUP_ACTIVIDAD]) en filas, meses en columnas y COSTO ACTIVIDAD y FRECUENCIA.
- **Gráfico de entidades**: Gráfico combinado con columnas de FACTURACIÓN por ENTIDAD (CUPS[NOMBRE_TERCERO]) de mayor a menor y una línea con el %UTILIDAD.

## Reglas de negocio
- **Fecha de inicio de costos**: Filtro de página CALENDARIO[Date] mayor o igual al 1 de septiembre de 2024.
- **Top de entidades**: El gráfico de entidades tiene un filtro Top N que deja las 10 CUPS[NOMBRE_TERCERO] con mayor suma de VLRTOTSERV.

## Observaciones
- **Página sin acceso**: Ningún botón lleva a esta página. Por confirmar si se debe eliminar.
- **Frecuencia de otra tabla**: La matriz cruza el costo de COSTOS con la frecuencia de CUPS; por confirmar que la relación entre ambas tablas sea por actividad.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
