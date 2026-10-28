---
tablero: TABLERO PERFIL DE MORBILIDAD
pagina: PERFIL DE MORBILIDAD
nombre_funcional: Atenciones y mortalidad por mes, edad, sexo, CMD y GRD
bloque: Histórico
tablas: [MATRIZ 2024, ONCOLOGICO]
actualizado: 2026-10-28
version: 2
id_pagina: 4a71645b0d74a42e3519
---

# PERFIL DE MORBILIDAD

## Propósito
Detalla los egresos por mes, rango de edad y sexo, y por CMD y GRD con sus defunciones y porcentaje de mortalidad. Sirve para identificar qué diagnósticos y grupos generan mayor carga asistencial y mortalidad. En pantalla se titula «PERFIL MORBILIDAD» y se llega desde el botón PERFIL DE MORBILIDAD de INICIO. Análisis por año y mes (bloque Histórico). La documentación original la llama «Detalle Perfil de Morbilidad».

## Fuentes de datos
- **MATRIZ 2024**: Egresos con mes, edad, sexo, CMD, GRD, servicio y estado del egreso.
- **ONCOLOGICO**: Marca de diagnóstico oncológico para el botón ONCOLOGICO.

## Indicadores
- **Atenciones**: Egresos del grupo. Conteo de filas de MATRIZ 2024; columna contada por confirmar.
- **% atenciones**: Atenciones del grupo sobre el total filtrado.
- **Promedio de edad**: Edad promedio en años. Promedio de MATRIZ 2024[Edad].
- **Defunciones**: Egresos con estado FALLECE. SUM(MATRIZ 2024[DEFUNCIONES]).
- **% defunciones**: Mortalidad del grupo. %DEFUNCIONES = SUM('MATRIZ 2024'[DEFUNCIONES])/COUNT('MATRIZ 2024'[Egreso_Cod_CIE10]).

## Visuales
- **Tabla por mes**: Mes (enero a diciembre) con ATENCIONES y total.
- **Tabla por rango de edad**: RANGO EDAD con ATENCIONES.
- **Tarjeta promedio de edad**: PROMEDIO (EDAD).
- **Tabla por sexo**: FEMENINO y MASCULINO con ATENCIONES y total.
- **Tabla por CMD**: CMD con ATENCIONES, %ATENCIONES, DEFUNCIONES y %DEFUNCIONES, con total.
- **Tabla por GRD**: GRD con las mismas columnas, ordenada por %ATENCIONES de mayor a menor.
- **Filtros de la página**: Segmentadores de Año, Mes y GRD, botón ONCOLOGICO y botones de servicio.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Defunción**: Estado del egreso «FALLECE» o «1».
- **Denominador de mortalidad**: %DEFUNCIONES divide por los egresos que tienen código CIE10 de egreso, no por todas las atenciones.

## Observaciones
- **Fila CMD vacía con «Infinito»**: En la captura la tabla de CMD tiene una fila sin CMD con cerca del 22 % de las atenciones y %DEFUNCIONES «Infinito», porque esos egresos no tienen código CIE10 de egreso (división por cero).
- **Tarjeta de egresos**: La documentación menciona tarjetas de promedio de edad y egresos totales; la captura solo muestra el promedio de edad.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP (solo modelo semántico).
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
