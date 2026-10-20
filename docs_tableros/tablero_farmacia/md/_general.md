---
tablero: TABLERO FARMACIA
pagina: GENERAL
nombre_funcional: Suministros pendientes, inventario mínimo, vencimientos y oportunidad de dispensación en farmacia
bloque: General
tablas: [PENDIENTES_FARMACIA, TIEMPOS_DISPENSACIÓN, CANTIDAD_MINIMA, VENCIMIENTO_PRODUCTOS, PRODUCTOS_VENCIDOS, ALMACENES]
actualizado: 2026-10-20
version: 1
---

# GENERAL

## Propósito
Monitorea la operación de la farmacia hospitalaria: suministros de medicamentos pendientes de dispensar, productos por debajo del inventario mínimo, medicamentos vencidos o próximos a vencer y la oportunidad de dispensación. Sirve para anticipar desabastecimientos y vencimientos y mejorar los tiempos de entrega. INICIO lleva con botones a SUMINISTROS PENDIENTES, inventario (STOCK MINIMO), MEDICAMENTOS VENCIDOS y TIEMPO DE DISPENSACIÓN.

## Fuentes de datos
- **PENDIENTES_FARMACIA**: Órdenes de medicamentos de pacientes hospitalizados (intrahospitalarias, tipo de orden 0) solicitadas desde hace 3 días hasta hoy en los almacenes de código 002, 007, 075 y 062; trae folio, medicamento, cantidad, servicio, marca MIPRES, fecha de solicitud, fecha de cierre (despacho) y rango de horas.
- **TIEMPOS_DISPENSACIÓN**: Tiempos de dispensación por documento con colaborador, servicio, fecha del folio (hcfecfol), fecha del documento (IDFECDOC) y oportunidad en horas (OportunidadHor). Su consulta no está en la documentación.
- **CANTIDAD_MINIMA**: Productos con su stock mínimo, la cantidad en Dinámica y la marca falta. Su consulta no está en la documentación.
- **VENCIMIENTO_PRODUCTOS**: Lotes de productos con fecha de vencimiento, meses para vencer (mes), lote, zona y cantidad; viene de la vista PRODUCTOS_VENCIDOS_FARMACIA.
- **PRODUCTOS_VENCIDOS**: Ajustes de inventario con concepto «MEDICAMENTOS VENCIDOS» de los últimos 3 meses en los almacenes 002, 007, 075, 062 y 082, con producto y cantidad.
- **ALMACENES**: Lista de almacenes (IALNOMBRE) para el filtro de almacén.

## Definiciones
- **Suministro pendiente**: Orden de medicamento sin fecha de cierre (PENDIENTES_FARMACIA[FECHA_CIERRE] vacía); se cuenta por folio de historia clínica (HCNFOLIO).
- **Tiempo de espera del suministro**: Minutos u horas desde la solicitud (HCSFECSOL) hasta el cierre (IDFECCON) o, si no hay cierre, hasta el momento de la actualización.
- **Horas de suministro**: Rango del tiempo de espera: 1. 0-6 horas, 2. 6-12 horas, 3. 12-18 horas, 4. 18-24 horas, 5. 24-36 horas y 6. 36 o mas horas.
- **Oportunidad de dispensación**: Tiempo promedio en horas para dispensar, AVERAGE(TIEMPOS_DISPENSACIÓN[OportunidadHor]); entre qué eventos se mide está por confirmar.
- **Producto bajo inventario mínimo**: Producto con CANTIDAD_MINIMA[falta] = 1; según la captura de STOCK MINIMO, su cantidad en Dinámica es menor que su stock mínimo.
- **Medicamento MIPRES**: Medicamento marcado en Dinámica como prescripción MIPRES (IPRMIPRESPR).

## Reglas de negocio
- **Almacenes de pendientes**: Solo almacenes con código 002, 007, 075 y 062; vencidos agrega el 082.
- **Ventana de pendientes**: Solicitudes desde hace 3 días hasta hoy.
- **Ventana de vencidos**: Ajustes por medicamentos vencidos de los últimos 3 meses.

## Observaciones
- **PBIP incompleto**: El PBIP no trae modelo semántico ni la lista de páginas; trae INICIO, STOCK MINIMO y MEDICAMENTOS VENCIDOS parciales y una página de tiempo de dispensación sin nombre. SUMINISTROS PENDIENTES no está y el botón INVENTARIO apunta a una página que no existe en el PBIP.
- **Consultas sin uso visible**: La documentación incluye las consultas PRODUCTOS_DESECHADOS y PRODUCTO, idénticas entre sí (concepto «MEDICAMENTOS DESECHADOS»), que no aparecen en ningún visual del PBIP.
- **Consultas no documentadas**: TIEMPOS_DISPENSACIÓN, CANTIDAD_MINIMA y ALMACENES se usan en visuales pero su consulta no está documentada.
- **Modo de las tablas**: El catálogo local indica modo import; por confirmar con el modelo.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
