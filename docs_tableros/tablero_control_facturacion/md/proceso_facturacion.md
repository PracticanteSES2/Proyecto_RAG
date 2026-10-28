---
tablero: TABLERO CONTROL FACTURACION
pagina: PROCESO FACTURACION
nombre_funcional: Egresos gestionados y gestiones por usuario en el proceso de facturación
bloque: Histórico
tablas: [FACTURACION_PERFILES, CALENDARIO]
actualizado: 2026-10-28
version: 2
---

# PROCESO FACTURACION

## Propósito
Muestra el volumen de trabajo del proceso de facturación: egresos gestionados, total facturado, número de gestiones por usuario y el tiempo promedio de gestión por mes comparando años. Permite filtrar por perfil. Análisis histórico; se llega desde el botón PROCESO FACTURACIÓN de INICIO y tiene botones a RESUMEN FACTURACION, TIEMPOS, TRAZABILIDAD y FACTURACION PENDIENTE. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **FACTURACION_PERFILES**: Una fila por cuenta y perfil (primera gestión de cada perfil) con responsables de recibe y entrega, fechas, paciente, entidad, tipo de ingreso, cama, servicio y estado de la factura. Egresos desde el 1 de agosto de 2025, AINESTADO 0 o 1. FECHA es la fecha de egreso.

## Indicadores
- **Egresos gestionados**: Número de egresos con gestión en el proceso. Medida exacta por confirmar (conteo distinto de ingresos).
- **Total facturado**: Valor facturado del periodo. Medida y columna por confirmar; la consulta documentada no trae montos.
- **Gestiones**: Número de gestiones (cuentas entregadas) por usuario. Agregación por confirmar.
- **Tiempo de gestión**: Promedio en horas de TIEMPO (horas entre recibe y entrega).
- **Nombre del usuario**: Columna NOMBRE_COMPLETO = CONCATENATE(NOM_ENTREGA, CONCATENATE(" ", AP_ENTREGA)); es quien entrega la cuenta.

## Visuales
- **Tarjetas**: EGRESOS GESTIONADOS y TOTAL FACTURADO.
- **Filtros**: Segmentadores de Año y Mes y lista de casillas PERFIL (AUDITORIA MEDICAMENTOS, AUDITORIA PERTINENCIA, CUENTAS, FACTURACION, GESTION DE LA INFORMACION Y ARCHIVO, RADICACION DE CUENTAS).
- **Tabla de gestiones por usuario**: Columnas NOMBRE_COMPLETO y GESTIONES.
- **Gráfico de líneas por mes y año**: Titulado «TIEMPO DE GESTIÓN por Mes y Año»; tiempo promedio de gestión por mes con una línea por año.
- **Botones de navegación**: RESUMEN FACTURACION, TIEMPOS, TRAZABILIDAD y FACTURACION PENDIENTE.

## Reglas de negocio
- **Primera gestión por perfil**: Cada cuenta aporta, por perfil, solo su primer recibe y su entrega.
- **Gestión por quien entrega**: Las gestiones se atribuyen al usuario que entrega la cuenta.

## Observaciones
- **Formato del total**: En la captura de la documentación TOTAL FACTURADO se ve como «7,96500 mil»; formato por revisar.
- **Unión de facturas**: La consulta une SLNFACTUR_DW sin agrupar; un ingreso con varias facturas puede duplicar filas. Por confirmar.
- **Mayúsculas**: En la tabla algunos nombres salen en mayúsculas y otros no, según el origen (historia o auditoría).
- **Sin página en el PBIP**: El PBIP local no trae una página llamada PROCESO FACTURACION: el botón PROCESO FACTURACIÓN de INICIO lleva a la página FACTURACION. La página «Duplicado de INICIO» (tabla NOMBRE COMPLETO y GESTIONES, MONTO FACTURADO, PERFIL, TIEMPO DE GESTIÓN) parece una versión de esta página. Por confirmar.
- **Tabla**: La documentación escribe FACTURACION_PERFILES; la tabla del modelo se llama 'FACTURACION PERFILES'.
- **Horas por día**: FACTURACION PERFILES convierte FECHA_RECIBE y FECHA_ENTREGA a fecha sin hora, por lo que el tiempo de gestión en horas es siempre un múltiplo de 24 (equivale a días por 24)

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
