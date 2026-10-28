---
tablero: TABLERO CONTROL FACTURACION
pagina: INICIO
nombre_funcional: Ingresos abiertos y valor estimado pendiente de facturar
bloque: Día
tablas: [ULT_GESTION]
actualizado: 2026-10-20
version: 1
---

# INICIO

## Propósito
Página principal del tablero. Muestra los ingresos abiertos (pacientes admitidos cuya cuenta aún no se cierra) y el valor estimado de sus servicios, por tipo de ingreso, servicio, aseguradora y mes de ingreso, para priorizar la gestión de facturación. Es una foto del estado actual (bloque Día). Tiene botones a DETALLE FACTURACIÓN (RESUMEN FACTURACION), PROCESO FACTURACION, FACTURACION PENDIENTE, TRAZABILIDAD y FACTURADORES. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **ULT_GESTION**: Una fila por ingreso con su última gestión de trazabilidad (perfil, responsable, fechas de recibe y entrega), paciente, entidad, tipo de ingreso, cama, servicio, área de servicio, valor estimado (FACTURADO), facturador y monto facturado. FECHA es la fecha de ingreso. Sin límite de fechas. Nombre de la tabla por confirmar (misma consulta que TRAZABILIDAD).

## Indicadores
- **Valor estimado**: Suma del valor de los servicios cargados a los ingresos abiertos, en pesos. Suma de la columna FACTURADO (SUM(SLNSERPRO.SERVALENT) por ingreso).
- **Ingresos abiertos**: Número de ingresos abiertos en el filtro. Medida exacta por confirmar (conteo de INGRESO).

## Visuales
- **Tarjetas**: VALOR ESTIMADO e INGRESOS ABIERTOS.
- **Filtros**: Segmentador AREA_SERVICIO, segmentadores de año y mes (ambos titulados «Date») y botones AMBULATORIO / HOSPITALARIO.
- **Gráfico de líneas por año y mes**: Titulado «VALOR ESTIMADO POR AÑO Y MES»; valor estimado por mes de ingreso, una línea para AMBULATORIO y otra para HOSPITALARIO.
- **Barras por servicio**: Titulado «VALOR ESTIMADO POR SERVICIO»; valor estimado por servicio (cama), separado en ambulatorio y hospitalario.
- **Treemap por aseguradora**: Titulado «VALOR ESTIMADO POR ASEGURADORA»; valor estimado por aseguradora.
- **Botones de navegación**: DETALLE FACTURACIÓN, PROCESO FACTURACIÓN, FACTURACION PENDIENTE, TRAZABILIDAD y FACTURADORES.

## Reglas de negocio
- **Ingreso abierto**: Ingreso con AINESTADO distinto de 1, 2 y 4 cuya última gestión no es RADICACION DE CUENTAS (perfil 17); se incluyen ingresos sin ninguna gestión.
- **Última gestión**: Para cada ingreso se toma la gestión con la fecha de entrega más reciente; solo cuentan gestiones posteriores o iguales a la fecha de egreso.
- **Valor estimado**: Suma de todos los servicios cargados al ingreso, facturados o no.

## Observaciones
- **Ingresos antiguos**: El gráfico mensual muestra ingresos abiertos desde 2023; la consulta no limita fechas.
- **Unión de auditorías**: La consulta une la trazabilidad (TFESTADOH.TFACTURACION) con el número de ingreso de la solicitud de auditoría; por confirmar si las llaves corresponden.
- **Títulos «Date»**: Los segmentadores de año y mes muestran el título genérico «Date».

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
