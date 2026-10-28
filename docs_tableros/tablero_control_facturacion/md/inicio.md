---
tablero: TABLERO CONTROL FACTURACION
pagina: INICIO
nombre_funcional: Ingresos abiertos y valor estimado pendiente de facturar
bloque: Día
tablas: [ULT_GESTION]
actualizado: 2026-10-28
version: 2
---

# INICIO

## Propósito
Página principal del tablero. Muestra los ingresos abiertos (pacientes admitidos cuya cuenta aún no se cierra) y el valor estimado de sus servicios, por tipo de ingreso, servicio, aseguradora y mes de ingreso, para priorizar la gestión de facturación. Es una foto del estado actual (bloque Día). Es la única página visible; tiene botones a DETALLE FACTURACIÓN (RESUMEN FACTURACION), PROCESO FACTURACIÓN (página FACTURACION), FACTURACION PENDIENTE, TRAZABILIDAD (página TRAZABILIDAD_H-A) y FACTURADORES.

## Fuentes de datos
- **ULT_GESTION**: Una fila por ingreso con su última gestión de trazabilidad (perfil, responsable, fechas de recibe y entrega), paciente, entidad, tipo de ingreso, cama, servicio, área de servicio, valor estimado (FACTURADO), facturador y monto facturado. FECHA es la fecha de ingreso. Sin límite de fechas. Es la misma tabla de TRAZABILIDAD.

## Indicadores
- **Valor estimado**: Suma del valor de los servicios cargados a los ingresos abiertos, en pesos. Suma de la columna FACTURADO (SUM(SLNSERPRO.SERVALENT) por ingreso).
- **Ingresos abiertos**: Número de ingresos abiertos: DISTINCTCOUNT(ULT_GESTION[INGRESO]). La tarjeta tiene filtros de visual sobre INGRESOS que, al no haber relación con ULT_GESTION, probablemente no afectan el conteo.

## Visuales
- **Tarjetas**: VALOR ESTIMADO e INGRESOS ABIERTOS.
- **Filtros**: Segmentadores «AREA_SERVICIO» (ULT_GESTION[AREA_SERVICIO], sin vacíos), «Date Año» y «Date Mes» (CALENDARIO[Date]) y «TIPO_INGRESO» (DIM_TIPO_INGRESO[TIPO_INGRESO], botones AMBULATORIO / HOSPITALARIO)
- **Gráfico de líneas por año y mes**: Titulado «VALOR ESTIMADO POR AÑO Y MES»; valor estimado por mes de ingreso, una línea para AMBULATORIO y otra para HOSPITALARIO.
- **Barras por servicio**: Titulado «VALOR ESTIMADO POR SERVICIO»; valor estimado por área de servicio (ULT_GESTION[AREA_SERVICIO]), separado en ambulatorio y hospitalario.
- **Treemap por aseguradora**: Titulado «VALOR ESTIMADO POR ASEGURADORA»; valor estimado por aseguradora (ULT_GESTION[TERNOMCOM])
- **Botones de navegación**: DETALLE FACTURACIÓN lleva a RESUMEN FACTURACION, PROCESO FACTURACIÓN a la página FACTURACION, FACTURACION PENDIENTE a su página, TRAZABILIDAD a TRAZABILIDAD_H-A y FACTURADORES a su página.

## Reglas de negocio
- **Ingreso abierto**: Ingreso con AINESTADO distinto de 1, 2 y 4 cuya última gestión no es RADICACION DE CUENTAS (perfil 17); se incluyen ingresos sin ninguna gestión.
- **Última gestión**: Para cada ingreso se toma la gestión con la fecha de entrega más reciente; solo cuentan gestiones posteriores o iguales a la fecha de egreso.
- **Valor estimado**: Suma de todos los servicios cargados al ingreso, facturados o no.

## Observaciones
- **Ingresos antiguos**: El gráfico mensual muestra ingresos abiertos desde 2023; la consulta no limita fechas.
- **Unión de auditorías**: La consulta une la trazabilidad (TFESTADOH.TFACTURACION) con el número de ingreso de la solicitud de auditoría; por confirmar si las llaves corresponden.
- **Títulos «Date»**: Los segmentadores de año y mes llevan los títulos genéricos «Date Año» y «Date Mes»

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
