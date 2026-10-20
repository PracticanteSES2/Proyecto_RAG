---
tablero: TABLERO CONTROL FACTURACION
pagina: EN PROCESO AUDITORIA MEDICAMENTOS
nombre_funcional: Cuentas en proceso de auditoría de medicamentos con semáforo de días
bloque: Día
tablas: [ENPROCESO_FACTURACION]
actualizado: 2026-10-20
version: 1
---

# EN PROCESO AUDITORIA MEDICAMENTOS

## Propósito
Hace seguimiento a las cuentas hospitalarias cuya etapa actual es la auditoría de medicamentos: cuántas siguen en proceso, cuántos días llevan y cuánto pasó entre la salida del paciente y la entrega, con semáforo de 0-7, 8-30 y 31 o más días. Es una foto del estado actual (bloque Día). Página oculta en Power BI; se llega por botón (origen por confirmar) y su botón de inicio vuelve al inicio del tablero.

## Fuentes de datos
- **ENPROCESO_FACTURACION**: Última etapa de cada cuenta (la de fecha de recibe más reciente) con egreso desde el 1 de agosto de 2025 y AINESTADO 0 o 1. Trae ingreso, paciente, entidad, tipo de ingreso, perfil, fechas de recibe, entrega y salida, estado de la factura y DIAS_EN_PROCESO.

## Indicadores
- **Promedio días en proceso**: Medida PROMEDIO_DIAS_PROCESO: promedio de DIAS_EN_PROCESO de las cuentas sin fecha de entrega. DAX: CALCULATE(AVERAGE(ENPROCESO_FACTURACION[DIAS_EN_PROCESO]), FILTER(ENPROCESO_FACTURACION, ISBLANK(ENPROCESO_FACTURACION[FECHA_ENTREGA]))). Unidad: días.
- **Facturas en proceso**: Medida PROCESO_FACTURACION: ingresos distintos sin fecha de entrega. DAX: CALCULATE(DISTINCTCOUNT(ENPROCESO_FACTURACION[INGRESO]), FILTER(ENPROCESO_FACTURACION, ISBLANK(ENPROCESO_FACTURACION[FECHA_ENTREGA]))).
- **Días en proceso**: Días desde que el perfil recibió la cuenta hasta la entrega, o hasta hoy si no se ha entregado. Si el perfil es ESTACION DE ENFERMERIA se cuenta desde la salida del paciente. Columna DIAS_EN_PROCESO.
- **Diferencia días salida vs entrega**: Días entre la salida del paciente y la entrega de la cuenta. Columna DIF_SALIDA_RECIBE = DATEDIFF(FECHA_SALIDA, FECHA_ENTREGA, DAY).

## Visuales
- **Encabezado y leyenda**: Título «FACTURAS EN PROCESO AUDITORIA DE MEDICAMENTOS» con la leyenda del semáforo: 0-7 DIAS verde, 8-30 DIAS amarillo, 31 DIAS O MAS rojo.
- **Tarjeta promedio de días**: PROMEDIO DIAS EN PROCESO (medida PROMEDIO_DIAS_PROCESO).
- **Tarjeta facturas en proceso**: PROCESO FACTURACION (medida PROCESO_FACTURACION), con filtro de visual ESTADO_FACTURA = OTRO.
- **Tabla diferencia días salida vs entrega**: Titulada «DIFERENCIA DÍAS SALIDA VS ENTREGA»; columnas INGRESO, NOMBRE, FECHA_ENTREGA, FECHA_SALIDA y DIFERENCIA DIAS (suma de DIF_SALIDA_RECIBE). Filtros: FECHA_ENTREGA vacía y ESTADO_FACTURA = OTRO.
- **Tabla días en proceso**: Titulada «DIAS EN PROCESO FACTURACION»; columnas INGRESO, NOMBRE, FECHA_RECIBE, FECHA_SALIDA y DIAS EN PROCESO (suma de DIAS_EN_PROCESO), ordenada de mayor a menor. Filtros: FECHA_ENTREGA no vacía y ESTADO_FACTURA = FACTURADA.

## Reglas de negocio
- **Filtro de página**: TIPO INGRESO = HOSPITALARIO y PERFIL = AUDITORIA MEDICAMENTOS.
- **Semáforo de días**: Verde de 0 a 7 días, amarillo de 8 a 30 y rojo de 31 a 1.000; aplica al fondo de DIFERENCIA DIAS y de DIAS EN PROCESO.
- **Etapa actual**: Cada ingreso aparece una sola vez, con el perfil que lo recibió de último.

## Observaciones
- **Filtros contradictorios**: Las tarjetas cuentan cuentas sin fecha de entrega, pero la tabla de días en proceso muestra solo cuentas con fecha de entrega y factura emitida; en la captura de la documentación la tarjeta de facturas en proceso sale «(En blanco)» y la tabla de diferencia vacía. Por confirmar el filtro correcto.
- **Valores sin color**: Diferencias negativas (entrega anterior a la salida) o mayores de 1.000 días quedan sin color.
- **Nombre engañoso**: La columna DIF_SALIDA_RECIBE usa la fecha de entrega, no la de recibe.
- **Reglas sobrantes**: Las tablas conservan reglas de formato de columnas de otro tablero (ADMISIONES_DIA, EN ESPERA INGRESO) que no se usan aquí.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
