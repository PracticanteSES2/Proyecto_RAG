---
tablero: TABLERO CONTROL FACTURACION
pagina: EN PROCESO AUDITORIA PERTINENCIA
nombre_funcional: Cuentas en proceso de auditoría de pertinencia con semáforo de días
bloque: Día
tablas: [ENPROCESO_FACTURACION]
actualizado: 2026-10-28
version: 2
---

# EN PROCESO AUDITORIA PERTINENCIA

## Propósito
Hace seguimiento a las cuentas cuya etapa actual es la auditoría de pertinencia: cuántas siguen en proceso, cuántos días llevan y cuánto pasó entre la salida del paciente y la entrega, con semáforo de 0-7, 8-30 y 31 o más días. Es una foto del estado actual (bloque Día). Página oculta en Power BI; se llega por el botón PROCESO FACTURACION de la página de tiempos del perfil AUDITORIA PERTINENCIA, y su botón de inicio vuelve a INICIO.

## Fuentes de datos
- **ENPROCESO_FACTURACION**: La misma tabla de EN PROCESO AUDITORIA MEDICAMENTOS (última etapa de cada cuenta con egreso desde el 1 de agosto de 2025); aquí se ven las cuentas del perfil AUDITORIA PERTINENCIA.

## Indicadores
- **Promedio días en proceso**: Medida PROMEDIO_DIAS_PROCESO: promedio de DIAS_EN_PROCESO de las cuentas sin fecha de entrega. Unidad: días.
- **Facturas en proceso**: Medida PROCESO_FACTURACION: ingresos distintos sin fecha de entrega.
- **Días en proceso**: Días desde que auditoría de pertinencia recibió la cuenta (asignación de la auditoría) hasta la entrega (respuesta), o hasta hoy. Columna DIAS_EN_PROCESO.
- **Diferencia días desde la salida**: Días que la cuenta lleva (o llevó) en el perfil: desde FECHA_RECIBE hasta FECHA_ENTREGA o hasta ahora si no se ha entregado. Columna DIF_SALIDA_RECIBE = DATEDIFF(FECHA_RECIBE, IF(ISBLANK(FECHA_ENTREGA), NOW(), FECHA_ENTREGA), DAY). No usa la fecha de salida del paciente, a pesar del título de la tabla.

## Visuales
- **Encabezado y leyenda**: Título «FACTURAS EN PROCESO AUDITORIA DE PERTINENCIA» con la leyenda 0-7 DIAS verde, 8-30 DIAS amarillo y 31 DIAS O MAS rojo.
- **Tarjetas**: PROMEDIO DIAS EN PROCESO (medida PROMEDIO_DIAS_PROCESO) y PROCESO FACTURACION (medida PROCESO_FACTURACION, sin filtro de estado de factura)
- **Tabla diferencia de días**: Titulada «DIFERENCIA DE DIAS DESDE FECHA SALIDA PACIENTE»; columnas INGRESO, NOMBRE, FECHA_ENTREGA, FECHA_SALIDA y DIFERENCIA DIAS.
- **Tabla días en proceso**: Titulada «DIAS EN PROCESO FACTURACION»; columnas INGRESO, NOMBRE, FECHA_RECIBE, FECHA_SALIDA y DIAS EN PROCESO con semáforo.

## Reglas de negocio
- **Filtro de página**: TIPO INGRESO = HOSPITALARIO y PERFIL = «AUDITORIA PERTINENCIA» (confirmado en el PBIP)
- **Semáforo de días**: Verde de 0 a 7 días, amarillo de 8 a 30 y rojo de 31 o más.

## Observaciones
- **Sin datos en la captura**: En la captura de la documentación las tarjetas salen «(En blanco)», la tabla de días en proceso vacía y la de diferencia muestra un caso con −288 días (entrega anterior a la salida). Por confirmar los filtros de los visuales.
- **Filtros por tabla**: A diferencia de las otras páginas EN PROCESO, la tabla DIAS EN PROCESO FACTURACION solo filtra FECHA_ENTREGA vacía y no filtra ESTADO_FACTURA, y la tabla de diferencia no tiene filtros de visual.
- **Título de la tabla de diferencia**: La tabla «DIFERENCIA DE DIAS DESDE FECHA SALIDA PACIENTE» (o «DIFERENCIA DÍAS SALIDA VS ENTREGA») mide desde FECHA_RECIBE, no desde la salida del paciente; la documentación original describía FECHA_SALIDA como inicio. Por confirmar cuál es la intención.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
