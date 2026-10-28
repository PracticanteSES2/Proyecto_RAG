---
tablero: TABLERO CONTROL FACTURACION
pagina: FACTURACION PENDIENTE
nombre_funcional: Egresos pendientes de iniciar el trámite de facturación
bloque: Día
tablas: [PENDIENTES_FACTURACION]
actualizado: 2026-10-28
version: 2
---

# FACTURACION PENDIENTE

## Propósito
Lista los pacientes que ya egresaron y cuya cuenta todavía no tiene trazabilidad de facturación, con los días que lleva pendiente cada una y el servicio donde estaba el paciente. Sirve para gestionar los pendientes por servicio. Es una foto del estado actual (bloque Día); se llega desde el botón FACTURACION PENDIENTE de INICIO o de PROCESO FACTURACION. Página oculta en Power BI.

## Fuentes de datos
- **PENDIENTES_FACTURACION**: Ingresos con egreso (ADEFECSAL) entre el 1 de agosto de 2025 y hoy, sin registro de trazabilidad en TFACTURACI, con AINESTADO 0 o 3 y AEEGRCORCU distinto de 1. Trae ingreso, fecha de ingreso, tipo de ingreso, paciente y documento, fecha de egreso, cama, servicio, fecha de la epicrisis y área de servicio.

## Indicadores
- **Pendientes**: Número de egresos pendientes de facturación: DISTINCTCOUNT(PENDIENTES_FACTURACION[INGRESO]). La tarjeta tiene filtros de visual sobre INGRESOS (unidades distintas de HOSPITALIZACION PARCIAL, QUIROFANO y URGENCIAS, ingreso facturado) que, al no haber relación con PENDIENTES_FACTURACION, probablemente no afectan el conteo.
- **Días pendiente**: Días desde el egreso hasta hoy. Columna PENDIENTES_FACTURACION[TIEMPO] = DATEDIFF(PENDIENTES_FACTURACION[ADEFECSAL], TODAY(), DAY).

## Visuales
- **Tarjeta**: PENDIENTES.
- **Filtros**: Segmentadores «DOCUMENTO» (PENDIENTES_FACTURACION[PACNUMDOC]) e «INGRESO» para buscar un caso, «SERVICIO» (PENDIENTES_FACTURACION[SERVICIO]) y «TIPO_INGRESO» (DIM_TIPO_INGRESO[TIPO_INGRESO], botones AMBULATORIO / HOSPITALARIO); botón de inicio que vuelve a INICIO.
- **Tabla de pacientes**: Columnas INGRESO, FECHA EGRESO, DOCUMENTO, PACIENTE, CAMA, SERVICIO y DIAS PENDIENTE, ordenada de más a menos días.
- **Botones por servicio**: Filtran la tabla por servicio: ATENCION DOMICILIARIA, CUARTO PISO NORTE, CUARTO PISO SUR, CUIDADO INTERMEDIO NORTE, CUIDADO INTERMEDIO SUR, HOSPITALIZACION NEONATOS, HOSPITALIZACION PARCIAL, OBSTETRICIA, QUINTO PISO NORTE, QUINTO PISO SUR, QUIROFANO, SEXTO PISO y UNIDAD DE CUIDADO INTENSIVO.

## Reglas de negocio
- **Egreso pendiente**: Egreso sin ningún registro en TFACTURACI, es decir, ninguna área ha recibido todavía la cuenta.
- **Exclusión de egresos**: Se excluyen egresos con AEEGRCORCU = 1. Significado del campo por confirmar.
- **Estados de ingreso**: Solo ingresos con AINESTADO 0 o 3. Significado de los códigos por confirmar.
- **Filtros de página**: PENDIENTES_FACTURACION[TIPO_INGRESO] = HOSPITALARIO y FACTURACION PERFILES[PERFIL] = FACTURACION (confirmado en el PBIP); el segundo no afecta a la tabla porque no hay relación entre ambas.

## Observaciones
- **Llave de trazabilidad**: Esta consulta une TFACTURACI por el OID del ingreso, mientras las demás consultas del tablero la unen por el consecutivo (AINCONSEC). Si la llave es el consecutivo, ingresos con trazabilidad podrían aparecer como pendientes. Por confirmar.
- **Sin filtro de año**: La página no tiene filtros de año o mes; muestra todos los pendientes desde agosto de 2025.
- **Botón AMBULATORIO**: La página filtra HOSPITALARIO, por lo que el botón AMBULATORIO del segmentador no muestra pendientes (el filtro de página y el segmentador se combinan). Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
