---
tablero: TABLERO FARMACIA
pagina: GENERAL
nombre_funcional: Suministros pendientes, inventario mínimo, vencimientos y oportunidad de dispensación en farmacia
bloque: General
tablas: [PENDIENTES_FARMACIA, TIEMPOS_DISPENSACIÓN, CANTIDAD_MINIMA, VENCIMIENTO_PRODUCTOS, PRODUCTOS_VENCIDOS, ALMACENES]
actualizado: 2026-10-28
version: 2
---

# GENERAL

## Propósito
Monitorea la operación de la farmacia hospitalaria: suministros de medicamentos pendientes de dispensar, productos por debajo del inventario mínimo, medicamentos vencidos o próximos a vencer y la oportunidad de dispensación. Sirve para anticipar desabastecimientos y vencimientos y mejorar los tiempos de entrega. INICIO lleva con botones a SUMINISTROS PENDIENTES, inventario (STOCK MINIMO), MEDICAMENTOS VENCIDOS y TIEMPO DE DISPENSACIÓN.

## Fuentes de datos
- **PENDIENTES_FARMACIA**: Órdenes de medicamentos de pacientes hospitalizados (intrahospitalarias, tipo de orden 0) solicitadas desde hace 3 días hasta hoy en los almacenes de código 002, 007, 075 y 062; trae folio, medicamento, cantidad, servicio, marca MIPRES, fecha de solicitud, fecha de cierre (despacho) y rango de horas.
- **TIEMPOS_DISPENSACIÓN**: Una fila por orden de medicamento hospitalaria con su documento de suministro (folios desde 2025-01-01 hasta hoy); trae colaborador (USUDESCRI), servicio (gasnombre), fecha del folio (hcfecfol), fecha del documento de suministro (IDFECDOC) y oportunidad en minutos y horas (OportunidadMin, OportunidadHor). Modo import.
- **CANTIDAD_MINIMA**: Productos por almacén (OID 2, 1074 y 62 de Dinámica) con stock mínimo (STOCKCANTI), existencia física en Dinámica (CANDINAMICA), faltante y marca falta. Modo DirectQuery.
- **VENCIMIENTO_PRODUCTOS**: Lotes de productos con fecha de vencimiento, meses para vencer (mes), lote, zona y cantidad; viene de la vista PRODUCTOS_VENCIDOS_FARMACIA.
- **PRODUCTOS_VENCIDOS**: Ajustes de inventario con concepto «MEDICAMENTOS VENCIDOS» de los últimos 3 meses en los almacenes 002, 007, 075, 062 y 082, con producto y cantidad.
- **ALMACENES**: Lista de almacenes (IALNOMBRE) para el filtro de almacén.
- **ALMACENES (filtro)**: Solo incluye los almacenes de código 002, 007, 075, 062 y 082; filtra a todas las tablas por OID. Modo DirectQuery.
- **PRODUCTO**: Catálogo de productos (IPRCODIGO, IPRDESCOR) de Dinámica; se relaciona con CANTIDAD_MINIMA por código y ningún visual lo usa.
- **PRODUCTOS_DESECHADOS**: Ajustes de inventario con concepto «MEDICAMENTOS DESECHADOS» de los últimos 3 meses; ningún visual la usa.
- **Consulta1**: Vista DIM_UNIDAD (código, nombre de unidad y área de servicio); sin relaciones ni visuales. Por confirmar su propósito.

## Definiciones
- **Suministro pendiente**: Orden de medicamento sin fecha de cierre (PENDIENTES_FARMACIA[FECHA_CIERRE] vacía); se cuenta por folio de historia clínica (HCNFOLIO).
- **Tiempo de espera del suministro**: Minutos desde la solicitud (HCSFECSOL) hasta el cierre (IDFECCON) o, si no hay cierre, hasta el momento de la actualización; está en PENDIENTES_FARMACIA[minutos] y se agrupa en HORAS_SUMINISTRO (horas enteras).
- **Horas de suministro**: Rango del tiempo de espera: 1. 0-6 horas, 2. 6-12 horas, 3. 12-18 horas, 4. 18-24 horas, 5. 24-36 horas y 6. 36 o mas horas.
- **Oportunidad de dispensación**: Tiempo promedio en horas entre la fecha del folio (hcfecfol) y la del documento de suministro (IDFECDOC); si la orden no tiene documento, hasta el momento de la consulta. Es AVERAGE(TIEMPOS_DISPENSACIÓN[OportunidadHor]).
- **Producto bajo inventario mínimo**: Producto con CANTIDAD_MINIMA[falta] = 1; según la captura de STOCK MINIMO, su cantidad en Dinámica es menor que su stock mínimo.
- **Medicamento MIPRES**: Medicamento marcado en Dinámica como prescripción MIPRES (IPRMIPRESPR).
- **Inventario mínimo y faltante**: El stock mínimo (STOCKCANTI) se compara con la existencia física en Dinámica (CANDINAMICA); el faltante es STOCKCANTI menos CANDINAMICA y es negativo si hay excedente.
- **Meses para vencer**: VENCIMIENTO_PRODUCTOS[mes]: meses que faltan para que venza el lote; mes 0 o 1 se rotula «0-30 días» y mes 2 a 4 «30-120 días».

## Reglas de negocio
- **Almacenes de pendientes**: Solo almacenes con código 002, 007, 075 y 062; vencidos agrega el 082.
- **Ventana de pendientes**: Solicitudes desde hace 3 días hasta hoy.
- **Ventana de vencidos**: Ajustes por medicamentos vencidos de los últimos 3 meses.

## Observaciones
- **PBIP incompleto**: El PBIP trae el modelo y las seis páginas, pero SUMINISTROS PENDIENTES y «Duplicado de STOCK MINIMO» están sin visuales, STOCK MINIMO solo trae el filtro y el botón, y no están las tarjetas de oportunidad ni la tabla de 30-120 días. Todas las páginas salvo INICIO están ocultas en modo vista; el botón INVENTARIO de INICIO lleva a «Duplicado de STOCK MINIMO».
- **Consultas sin uso visible**: La documentación describe PRODUCTO igual que PRODUCTOS_DESECHADOS, pero en el modelo PRODUCTO es el catálogo de productos. Ninguna de las dos aparece en un visual; tampoco Consulta1.
- **Consultas no documentadas**: Las consultas de TIEMPOS_DISPENSACIÓN, CANTIDAD_MINIMA y ALMACENES no están en la documentación del propietario; se tomaron del modelo. La vista PRODUCTOS_VENCIDOS_FARMACIA tampoco se documenta.
- **Modo de las tablas**: TIEMPOS_DISPENSACIÓN y Consulta1 están en modo import; las demás tablas, en DirectQuery.
- **Nombre de la página de dispensación**: La página de oportunidad se llama OPORTUNIDAD DISPENSACIÓN en Power BI; el botón de INICIO se rotula TIEMPO DE DISPENSACIÓN.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
