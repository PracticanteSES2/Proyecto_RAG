---
tablero: TABLERO PERFIL DE MORBILIDAD
pagina: FACTURACION
nombre_funcional: Atenciones y facturación por CMD, GRD y CIE10
bloque: Histórico
tablas: [MATRIZ 2024, FACTURACION, ONCOLOGICO]
actualizado: 2026-10-28
version: 2
---

# FACTURACION

## Propósito
Cruza los egresos con la facturación: para cada CMD, GRD y diagnóstico CIE10 muestra las atenciones, su peso porcentual, el valor facturado y su peso, y el promedio de facturación. Sirve para ver qué diagnósticos y grupos aportan más ingresos a la institución. Se llega desde el botón FACTURACIÓN de INICIO. Análisis por año y mes (bloque Histórico).

## Fuentes de datos
- **MATRIZ 2024**: Egresos con CMD, GRD, CIE10, asegurador, sexo y servicio.
- **FACTURACION**: Valor neto de facturas válidas por número de ingreso; se cruza con los egresos por ingreso.
- **ONCOLOGICO**: Marca de diagnóstico oncológico para el botón ONCOLOGICO.

## Indicadores
- **Atenciones**: Egresos del grupo. Conteo de filas de MATRIZ 2024; columna contada por confirmar.
- **% atenciones**: Atenciones del grupo sobre el total de atenciones filtradas.
- **Facturación**: Valor neto facturado en pesos. SUM(FACTURACION[VALOR_FACTURA]).
- **% facturación**: Facturación del grupo sobre la facturación total filtrada.
- **Promedio de facturación**: Valor promedio en pesos; según las cifras de la captura es el promedio por factura (AVERAGE de FACTURACION[VALOR_FACTURA]) y no por atención. Por confirmar.

## Visuales
- **Filtros de la página**: Segmentadores de Año, Mes, Asegurador, GRD y Sexo (FEMENINO, MASCULINO), botón ONCOLOGICO y botones de servicio (GINECO, HOSPITALIZACION, HOSPITALIZACION PARCIAL, NEONATOS, SALA AZUL, UCI/UCIN, URGENCIAS).
- **Tabla por CMD**: CMD con ATENCIONES, %ATENCIONES, PROMEDIO DE FACTURACIÓN, FACTURACIÓN y %FACTURACIÓN, con total.
- **Tabla por GRD**: Mismas columnas por GRD, ordenada por %ATENCIONES de mayor a menor.
- **Tabla por CIE10**: Mismas columnas por diagnóstico CIE10, ordenada por ATENCIONES de mayor a menor.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Facturas consideradas**: Facturas en estado 1 y no anuladas, de ingresos desde 2024-01-01 con estado distinto de 2 y 4.
- **Cruce por ingreso**: La relación FACTURACION–MATRIZ 2024 es de muchos a muchos y filtra en ambos sentidos; cada grupo suma las facturas de sus ingresos.

## Observaciones
- **Cruce incompleto en 2025**: Los egresos de 2025 en adelante usan el identificador interno del ingreso y FACTURACION el consecutivo, así que su facturación podría no aparecer. Por confirmar.
- **Filtro de día anunciado**: La documentación menciona un filtro por día que no aparece en la captura.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP (solo modelo semántico).
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
