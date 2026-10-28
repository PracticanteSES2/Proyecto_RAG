---
tablero: TABLERO FINANCIERA
pagina: Duplicado de Duplicado de COSTOS X MESES
nombre_funcional: Venta, costo unitario y rentabilidad por CUPS (copia sin acceso)
bloque: Histórico
tablas: [CUPS, COSTOS, ACTIVIDADES, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# Duplicado de Duplicado de COSTOS X MESES

## Propósito
Muestra la venta, el costo, la rentabilidad y la frecuencia por CUPS desde septiembre de 2024, con tarjetas de totales y una tabla con precio de venta, costo unitario y rentabilidad por CUPS. Es una copia de COSTOS X MESES; página oculta sin ningún botón que llegue a ella.

## Fuentes de datos
- **CUPS**: Valor facturado (VLRTOTSERV), CANTIDAD, pagador (TERCERO) y medidas PRECIO_VENTA y Prueba CostoUnitario.
- **COSTOS**: Actividad (CUP_ACTIVIDAD) y costo de la actividad (COSTOACTIVIDAD).
- **ACTIVIDADES**: Código (SIPCODCUP) y descripción (SIPDESCUP) del CUPS.
- **CALENDARIO**: Fecha del filtro de página, jerarquía de año y mes y medidas COSTO_TOTAL, UTILIDAD_MONETARIA y %UTILIDAD.

## Indicadores
- **Ventas**: Suma de CUPS[VLRTOTSERV], tarjeta VENTAS. Unidad: pesos.
- **Costo total**: Medida CALENDARIO[COSTO_TOTAL], tarjeta COSTOS. Unidad: pesos. Cálculo: Por confirmar.
- **Utilidad monetaria**: Medida CALENDARIO[UTILIDAD_MONETARIA], tarjeta y columna RENTABILIDAD. Unidad: pesos. Cálculo: Por confirmar.
- **Frecuencia**: Suma de CUPS[CANTIDAD], tarjeta y columna FRECUENCIA. Unidad: cantidad de servicios.
- **Precio de venta**: Medida CUPS[PRECIO_VENTA], columna VENTA. Unidad: pesos. Cálculo: Por confirmar.
- **Costo unitario**: Promedio de COSTOS[COSTOACTIVIDAD], columna COSTO UNITARIO. Unidad: pesos.
- **Prueba costo unitario**: Medida CUPS[Prueba CostoUnitario], columna con el nombre técnico. Unidad: pesos. Cálculo: Por confirmar.
- **Porcentaje de utilidad**: Medida CALENDARIO[%UTILIDAD], columna %RENTABILIDAD. Unidad: porcentaje. Cálculo: Por confirmar.

## Visuales
- **Botón inicio**: Imagen arriba a la izquierda que vuelve a INICIO.
- **Segmentadores de año y mes**: Listas desplegables de año y de mes; el de año no ofrece 2023.
- **Segmentador CUPS**: Lista desplegable CUPS (COSTOS[CUP_ACTIVIDAD]).
- **Segmentador pagador**: Lista desplegable PAGADOR (CUPS[TERCERO]).
- **Tarjetas de totales**: Cuatro tarjetas con el valor completo: VENTAS, COSTOS, RENTABILIDAD y FRECUENCIA.
- **Tabla rentabilidad por CUPS**: Tabla con SIPCODCUP, SIPDESCUP, Prueba CostoUnitario, VENTA, COSTO UNITARIO, RENTABILIDAD, %RENTABILIDAD y FRECUENCIA, ordenada por frecuencia de mayor a menor y sin fila de totales.

## Reglas de negocio
- **Fecha de inicio de costos**: Filtro de página CALENDARIO[Date] mayor o igual al 1 de septiembre de 2024.
- **Cantidad mínima**: Filtro de página CUPS[CANTIDAD] mayor o igual a 1.
- **Solo CUPS con costo**: La tabla excluye las filas cuyo costo unitario está vacío.
- **Barras de rentabilidad**: RENTABILIDAD (rango automático) y %RENTABILIDAD (máximo 1) tienen barras de datos: verde (#97d966) si es positiva y rojo (#F65B40) si es negativa.

## Observaciones
- **Página sin acceso**: Ningún botón lleva a esta página. Por confirmar si se debe eliminar.
- **Medida de prueba visible**: La columna Prueba CostoUnitario conserva su nombre técnico y parece una prueba. Por confirmar si debe quedar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
