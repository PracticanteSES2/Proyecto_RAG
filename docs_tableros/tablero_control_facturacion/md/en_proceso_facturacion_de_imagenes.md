---
tablero: TABLERO CONTROL FACTURACION
pagina: EN PROCESO FACTURACION DE IMAGENES
nombre_funcional: Cuentas en proceso de facturación de imágenes con semáforo de días
bloque: Día
tablas: [ENPROCESO_FACTURACION]
actualizado: 2026-10-28
version: 2
---

# EN PROCESO FACTURACION DE IMAGENES

## Propósito
Hace seguimiento a las cuentas cuya etapa actual es la facturación de imágenes: cuántas siguen en proceso, cuántos días llevan y cuánto pasó entre la salida del paciente y la entrega, con semáforo de 0-7, 8-30 y 31 o más días. Es una foto del estado actual (bloque Día). Página oculta en Power BI; se llega por el botón PROCESO FACTURACION de la página de tiempos del perfil FACTURACION IMAGENES, y su botón de inicio vuelve a INICIO.

## Fuentes de datos
- **ENPROCESO_FACTURACION**: La misma tabla de EN PROCESO AUDITORIA MEDICAMENTOS (última etapa de cada cuenta con egreso desde el 1 de agosto de 2025); aquí se ven las cuentas del perfil FACTURACION IMAGENES.

## Indicadores
- **Promedio días en proceso**: Medida PROMEDIO_DIAS_PROCESO: promedio de DIAS_EN_PROCESO de las cuentas sin fecha de entrega. Unidad: días.
- **Facturas en proceso**: Medida PROCESO_FACTURACION: ingresos distintos sin fecha de entrega.
- **Días en proceso**: Días desde que facturación de imágenes recibió la cuenta hasta la entrega, o hasta hoy. Columna DIAS_EN_PROCESO.
- **Diferencia días desde la salida**: Días que la cuenta lleva (o llevó) en el perfil: desde FECHA_RECIBE hasta FECHA_ENTREGA o hasta ahora si no se ha entregado. Columna DIF_SALIDA_RECIBE = DATEDIFF(FECHA_RECIBE, IF(ISBLANK(FECHA_ENTREGA), NOW(), FECHA_ENTREGA), DAY). No usa la fecha de salida del paciente, a pesar del título de la tabla.

## Visuales
- **Encabezado y leyenda**: Título «FACTURAS EN PROCESO FACTURACION DE IMAGENES» con la leyenda 0-7 DIAS verde, 8-30 DIAS amarillo y 31 DIAS O MAS rojo.
- **Tarjetas**: PROMEDIO DIAS EN PROCESO (medida PROMEDIO_DIAS_PROCESO) y PROCESO FACTURACION (medida PROCESO_FACTURACION, con filtro de visual ESTADO_FACTURA distinto de FACTURADA)
- **Tabla diferencia de días**: Titulada «DIFERENCIA DE DIAS DESDE FECHA SALIDA PACIENTE»; columnas INGRESO, NOMBRE, FECHA_ENTREGA, FECHA_SALIDA y DIFERENCIA DIAS.
- **Tabla días en proceso**: Titulada «DIAS EN PROCESO FACTURACION»; columnas INGRESO, NOMBRE, FECHA_RECIBE, FECHA_SALIDA y DIAS EN PROCESO con semáforo.

## Reglas de negocio
- **Filtro de página**: TIPO INGRESO = HOSPITALARIO y PERFIL = «FACTURACION IMAGENES» (confirmado en el PBIP)
- **Semáforo de días**: Verde de 0 a 7 días, amarillo de 8 a 30 y rojo de 31 o más.

## Observaciones
- **Título de la tabla de diferencia**: La tabla «DIFERENCIA DE DIAS DESDE FECHA SALIDA PACIENTE» (o «DIFERENCIA DÍAS SALIDA VS ENTREGA») mide desde FECHA_RECIBE, no desde la salida del paciente; la documentación original describía FECHA_SALIDA como inicio. Por confirmar cuál es la intención.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
