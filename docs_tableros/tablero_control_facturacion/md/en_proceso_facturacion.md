---
tablero: TABLERO CONTROL FACTURACION
pagina: EN PROCESO FACTURACION
nombre_funcional: Cuentas en proceso en el área de facturación con semáforo de días
bloque: Día
tablas: [ENPROCESO_FACTURACION]
actualizado: 2026-10-20
version: 1
---

# EN PROCESO FACTURACION

## Propósito
Hace seguimiento a las cuentas cuya etapa actual es el área de facturación: cuántas siguen en proceso, cuántos días llevan desde que las recibió facturación y cuánto pasó desde la salida del paciente, con semáforo de 0-7, 8-30 y 31 o más días. Es una foto del estado actual (bloque Día). No confundir con FACTURACION (tiempos históricos del perfil) ni con PROCESO FACTURACION (gestiones por usuario). Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **ENPROCESO_FACTURACION**: La misma tabla de EN PROCESO AUDITORIA MEDICAMENTOS (última etapa de cada cuenta con egreso desde el 1 de agosto de 2025); aquí se ven las cuentas del perfil FACTURACION.

## Indicadores
- **Promedio días en proceso**: Medida PROMEDIO_DIAS_PROCESO: promedio de DIAS_EN_PROCESO de las cuentas sin fecha de entrega. Unidad: días.
- **Facturas en proceso**: Medida PROCESO_FACTURACION: ingresos distintos sin fecha de entrega.
- **Días en proceso**: Días desde que facturación recibió la cuenta hasta la entrega, o hasta hoy. Columna DIAS_EN_PROCESO.
- **Diferencia días desde la salida**: Días entre la salida del paciente y la entrega de la cuenta. Columna DIF_SALIDA_RECIBE.

## Visuales
- **Encabezado y leyenda**: Título «FACTURAS EN PROCESO FACTURACION» con la leyenda 0-7 DIAS verde, 8-30 DIAS amarillo y 31 DIAS O MAS rojo.
- **Tarjetas**: PROMEDIO_DIAS_PROCESO y PROCESO FACTURACION.
- **Tabla diferencia de días**: Titulada «DIFERENCIA DE DIAS DESDE FECHA SALIDA PACIENTE»; columnas AINCONSEC (ingreso), NOMBRE, FECHA_ENTREGA, FECHA_SALIDA y DIFERENCIA DIAS con semáforo, de mayor a menor.
- **Tabla días en proceso**: Titulada «DIAS EN PROCESO FACTURACION»; columnas AINCONSEC, NOMBRE, FECHA_RECIBE, FECHA_SALIDA y DIAS EN PROCESO con semáforo, de mayor a menor.

## Reglas de negocio
- **Filtro de página**: PERFIL = FACTURACION (incluye los códigos 2 y 13). Por confirmar si además filtra tipo de ingreso.
- **Semáforo de días**: Verde de 0 a 7 días, amarillo de 8 a 30 y rojo de 31 o más.

## Observaciones
- **Rótulo técnico**: La tarjeta de promedio muestra el nombre técnico PROMEDIO_DIAS_PROCESO en lugar de «PROMEDIO DIAS EN PROCESO» como en las demás páginas EN PROCESO.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
