---
tablero: TABLERO CVC
pagina: GENERAL
nombre_funcional: Variación de costos de compra de medicamentos, dispositivos e insumos
bloque: General
tablas: [COSTOS_PRODUCTOS]
actualizado: 2026-10-28
version: 2
---

# GENERAL

## Propósito
Tablero de una página para monitorear el comportamiento de los precios de compra de medicamentos, dispositivos médicos, insumos y otros productos del almacén 062 desde enero de 2025. Identifica qué productos subieron, bajaron o mantuvieron su costo frente a la compra anterior y el impacto en el valor comprado.

## Fuentes de datos
- **COSTOS_PRODUCTOS**: Registros de costo de productos (COSTO_PRODUCTOS_DW) del almacén 062 desde 2025-01-01, con producto, código, CUM, grupo, categoría, cantidad, último costo, costo promedio y costo y fecha del registro anterior del mismo producto y almacén.
- **COSTOS_VARIACION**: Segunda consulta que deja, por producto, el último costo y el costo anterior distinto con su fecha (el mayor costo distinto del último, no el inmediatamente previo).
- **DESABASTECIDOS**: Tercera consulta con la solicitud de desabastecimiento más reciente por producto (categoría 325, estados 1, 2 o 3), la misma fuente de DETALLE MEDICAMENTOS DESABASTECIDOS del BRIEFING HOSPITALARIO.
- **PRODUCTOS_REGULADOS**: Listado en Excel «Regulados y No Regulados Dinamica Gerencial» (hoja «Listado Productos Dinamica») con la marca de producto regulado; se une por IPRCODIGO.

## Definiciones
- **Costo actual**: Último costo registrado del producto en el registro (ULTIMOCOSTO).
- **Costo anterior**: Costo del registro inmediatamente anterior del mismo producto en el mismo almacén (COSTO_ANTERIOR).
- **Precio promedio anual**: Promedio de ULTIMOCOSTO del mismo producto en el mismo año (PrecioPromedioAnual_Col).
- **Clasificación de producto**: Categoría por grupo de inventario: INSUMOS Y MEDICAMENTOS, ASEO CAFETERIA REPUESTOS DOTACION, LABORATORIO CLINICO, OSTEOSINTESIS, OTROS SIN APLICACIÓN A COSTEO y VARIOS.

## Reglas de negocio
- **Almacén**: Solo registros del almacén con código 062.
- **Periodo**: Registros con fecha (FECHAREG) desde el 2025-01-01 hasta hoy.
- **Categoría por grupo**: La columna CATEGORIA asigna la clasificación según el código de grupo de inventario (IGRCODIGO); grupos no listados quedan vacíos.

## Observaciones
- **Sigla CVC**: El significado de la sigla CVC no está documentado. Por confirmar.
- **Almacén 062**: A qué almacén corresponde el código 062 está por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
