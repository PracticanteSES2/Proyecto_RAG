---
tablero: TABLERO CONTROL FACTURACION
pagina: TRAZABILIDAD
nombre_funcional: Última gestión de cada cuenta abierta y valor estimado por servicio
bloque: Día
tablas: [ULT_GESTION]
actualizado: 2026-10-20
version: 1
---

# TRAZABILIDAD

## Propósito
Muestra en qué etapa va cada cuenta abierta: quién la tiene (responsable), en qué perfil, desde cuándo, quién la facturó y su asegurador, separado en ambulatorio y hospitalario, más el valor estimado por servicio. Sirve para ubicar una cuenta y hacer seguimiento a los responsables. Foto del estado actual (bloque Día); se llega desde el botón TRAZABILIDAD de INICIO o de PROCESO FACTURACION. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **ULT_GESTION**: Ingresos abiertos con su última gestión de trazabilidad; es la misma consulta de INICIO (ver INICIO). Sin límite de fechas.

## Indicadores
- **Valor estimado**: Suma del valor de los servicios cargados a los ingresos abiertos (columna FACTURADO), en pesos.
- **Responsable**: Persona que recibió la cuenta en la última gestión. Columna ULT_GESTION[RESPONSABLE] = CONCATENATE(NOM_RECIBE, CONCATENATE(" ", AP_RECIBE)).

## Visuales
- **Tarjeta**: VALOR ESTIMADO.
- **Filtros**: Segmentadores RESPONSABLE, PERFIL, SERVICIO e INGRESO.
- **Tabla facturación ambulatorio**: Titulada «FACTURACION AMBULATORIO»; columnas INGRESO, RESPONSABLE, FACTURADOR, PERFIL, FECHA RECEPCIÓN, SERVICIO, CAMA y ASEGURADOR para ingresos ambulatorios.
- **Tabla facturación hospitalario**: Titulada «FACTURACION HOSPITALARIO»; mismas columnas para ingresos hospitalarios.
- **Treemap por servicio**: Titulado «VALOR ESTIMADO por SERVICIO»; valor estimado por servicio de la cama.

## Reglas de negocio
- **Cuenta abierta**: Igual que en INICIO: AINESTADO distinto de 1, 2 y 4 y última gestión distinta de RADICACION DE CUENTAS (perfil 17).
- **Última gestión**: La de fecha de entrega más reciente, posterior o igual a la fecha de egreso.

## Observaciones
- **Nombre de la tarjeta**: La documentación llama a la tarjeta «Total facturación», pero el tablero la titula VALOR ESTIMADO y suma valores cargados, no facturados.
- **Filas sin gestión**: En la captura de la documentación muchas filas no tienen responsable, perfil ni fecha de recepción (ingresos sin trazabilidad).
- **Servicio en blanco**: La porción más grande del treemap es «(En blanco)»: ingresos sin cama asignada, por ejemplo ambulatorios.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
