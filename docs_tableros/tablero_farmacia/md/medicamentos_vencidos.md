---
tablero: TABLERO FARMACIA
pagina: MEDICAMENTOS VENCIDOS
nombre_funcional: Medicamentos vencidos y próximos a vencer
bloque: Día
tablas: [VENCIMIENTO_PRODUCTOS, PRODUCTOS_VENCIDOS, ALMACENES]
actualizado: 2026-10-20
version: 1
---

# MEDICAMENTOS VENCIDOS

## Propósito
Controla los medicamentos próximos a vencer (a corto y mediano plazo) y los ya dados de baja por vencimiento, para priorizar su uso, rotación o disposición. Muestra el estado actual del inventario (bloque Día). Se llega desde el botón MEDICAMENTOS VENCIDOS de INICIO.

## Fuentes de datos
- **VENCIMIENTO_PRODUCTOS**: Lotes con fecha de vencimiento, meses para vencer, lote, zona y cantidad.
- **PRODUCTOS_VENCIDOS**: Ajustes de inventario por medicamentos vencidos de los últimos 3 meses.
- **ALMACENES**: Lista de almacenes para el filtro.

## Indicadores
- **Medicamentos en vencimiento 0-30 días**: Productos distintos con mes para vencer 0 o 1. DISTINCTCOUNT(VENCIMIENTO_PRODUCTOS[IPRCODIGO]) con mes <= 1.
- **Medicamentos en vencimiento 30-120 días**: Productos distintos con mes para vencer 2, 3 o 4. DISTINCTCOUNT(VENCIMIENTO_PRODUCTOS[IPRCODIGO]) con mes en 2, 3 y 4.
- **Medicamentos vencidos**: Total de medicamentos dados de baja por vencimiento; cálculo por confirmar (en INICIO es SUM(PRODUCTOS_VENCIDOS[iddcantid])).

## Visuales
- **Tarjetas de indicadores**: MEDICAMENTOS EN VENCIMIENTO 0-30 DÍAS, MEDICAMENTOS EN VENCIMIENTO 30-120 DÍAS y MEDICAMENTOS VENCIDOS.
- **Filtro de almacén**: Lista desplegable ALMACEN.
- **Tabla vencimiento 0-30 días**: Titulada «PRODUCTOS EN VENCIMIENTO ENTRE 0-30 DÍAS»; código, producto, FECHA VENCIMIENTO, MESES PARA VENCIMIENTO, LOTE, ZONA y CANTIDAD (suma de IFICANTID), con mes <= 1.
- **Tabla productos vencidos**: Titulada «PRODUCTOS VENCIDOS»; código, producto, CANTIDAD (suma de iddcantid) y FECHA VENCIMIENTO.
- **Tabla vencimiento 30-120 días**: Titulada «PRODUCTOS EN VENCIMIENTO ENTRE 30-120 DÍAS»; mismas columnas que la de 0-30 días para los meses 2 a 4.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Vencidos**: Ajustes de inventario con concepto «MEDICAMENTOS VENCIDOS» (tipos de ajuste 13 y 37) en los almacenes 002, 007, 075, 062 y 082.

## Observaciones
- **Días frente a meses**: Los rangos se rotulan en días pero se filtran por meses para vencer (0-1 y 2-4); según cómo calcule la vista el mes, «0-30 días» puede incluir productos que vencen en hasta unos 60 días. Por confirmar.
- **Fecha de vencidos**: La columna FECHA VENCIMIENTO de la tabla PRODUCTOS VENCIDOS es la fecha del documento de ajuste (IDFECDOC), no la fecha de vencimiento del lote.
- **Visuales fuera del PBIP**: La tarjeta MEDICAMENTOS VENCIDOS y la tabla de 30-120 días están en la captura pero no en el PBIP disponible.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
