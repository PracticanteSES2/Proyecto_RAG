---
tablero: TABLERO CONTROL FACTURACION
pagina: TRAZABILIDAD
nombre_funcional: Última gestión de cada cuenta abierta y valor estimado por servicio
bloque: Día
tablas: [ULT_GESTION]
actualizado: 2026-10-28
version: 2
---

# TRAZABILIDAD

## Propósito
Muestra en qué etapa va cada cuenta abierta: quién la tiene (responsable), en qué perfil, desde cuándo, quién la facturó, su asegurador y el valor estimado, más el valor estimado por servicio. Foto del estado actual (bloque Día). Página oculta en Power BI; solo tiene botón de inicio hacia INICIO y ningún botón del PBIP lleva a ella (el botón TRAZABILIDAD de INICIO va a TRAZABILIDAD_H-A).

## Fuentes de datos
- **ULT_GESTION**: Ingresos abiertos con su última gestión de trazabilidad; es la misma consulta de INICIO (ver INICIO). Sin límite de fechas.

## Indicadores
- **Valor estimado**: Suma del valor de los servicios cargados a los ingresos abiertos (columna FACTURADO), en pesos.
- **Responsable**: Persona que recibió la cuenta en la última gestión. Columna ULT_GESTION[RESPONSABLE] = CONCATENATE(NOM_RECIBE, CONCATENATE(" ", AP_RECIBE)).

## Visuales
- **Tarjeta**: VALOR ESTIMADO: suma de ULT_GESTION[FACTURADO], con filtro de visual INGRESOS[FACTURADO] = 1 que probablemente no tiene efecto.
- **Filtros**: Segmentadores «RESPONSABLE», «PERFIL», «SERVICIO» e «INGRESO» (ULT_GESTION[AINCONSEC]); botón de inicio que vuelve a INICIO.
- **Treemap por servicio**: Treemap con SERVICIO (ULT_GESTION[SERVICIO]) y VALOR ESTIMADO: valor estimado por servicio de la cama.
- **Tabla de ingresos**: Tabla sin título con columnas INGRESO, RESPONSABLE, FACTURADOR, PERFIL, FECHA RECEPCIÓN (FECHA_ENTREGA), SERVICIO, CAMA, ASEGURADOR (ENTIDAD) y VALOR ESTIMADO. La separación en tablas AMBULATORIO y HOSPITALARIO está en la página TRAZABILIDAD_H-A.

## Reglas de negocio
- **Última gestión**: La de fecha de entrega más reciente, posterior o igual a la fecha de egreso.
- **Filtros de página**: ULT_GESTION[AINESTADO] en (0, 3) y ULT_GESTION[PERFIL] distinto de FACTURACION IMAGENES (confirmado en el PBIP)
- **Cuenta abierta**: La tabla ULT_GESTION ya excluye AINESTADO 1, 2 y 4 y la última gestión RADICACION DE CUENTAS (perfil 17); esta página además deja solo AINESTADO 0 y 3 y quita FACTURACION IMAGENES.

## Observaciones
- **Nombre de la tarjeta**: La documentación llama a la tarjeta «Total facturación», pero el tablero la titula VALOR ESTIMADO y suma valores cargados, no facturados.
- **Filas sin gestión**: En la captura de la documentación muchas filas no tienen responsable, perfil ni fecha de recepción (ingresos sin trazabilidad).
- **Servicio en blanco**: La porción más grande del treemap es «(En blanco)»: ingresos sin cama asignada, por ejemplo ambulatorios.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
