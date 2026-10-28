---
tablero: TABLERO CONTROL FACTURACION
pagina: TRAZABILIDAD_H-A
nombre_funcional: Última gestión de cada cuenta abierta separada en ambulatorio y hospitalario
bloque: Día
tablas: [ULT_GESTION]
actualizado: 2026-10-28
version: 1
---

# TRAZABILIDAD_H-A

## Propósito
Muestra la última gestión de cada cuenta abierta en dos tablas, FACTURACION AMBULATORIO y FACTURACION HOSPITALARIO, con responsable, facturador, perfil, fecha de recepción, servicio, cama y asegurador, más el valor estimado por servicio. Foto del estado actual (bloque Día). Página oculta en Power BI; es el destino del botón TRAZABILIDAD de INICIO y su botón de inicio vuelve a INICIO.

## Fuentes de datos
- **ULT_GESTION**: Una fila por ingreso abierto con su última gestión de trazabilidad, igual que en INICIO y TRAZABILIDAD. Sin límite de fechas.

## Indicadores
- **Valor estimado**: Suma de ULT_GESTION[FACTURADO], el valor de los servicios cargados a los ingresos, en pesos. La tarjeta tiene un filtro de visual sobre INGRESOS que probablemente no la afecta.
- **Responsable**: Persona que recibió la cuenta en la última gestión. Columna ULT_GESTION[RESPONSABLE] = CONCATENATE(NOM_RECIBE, CONCATENATE(" ", AP_RECIBE))

## Visuales
- **Tarjeta**: VALOR ESTIMADO.
- **Filtros**: Segmentadores «RESPONSABLE», «PERFIL», «SERVICIO» e «INGRESO» (ULT_GESTION[AINCONSEC]); botón de inicio que vuelve a INICIO.
- **Tabla facturación ambulatorio**: Titulada «FACTURACION AMBULATORIO»; columnas INGRESO, RESPONSABLE, FACTURADOR, PERFIL, FECHA RECEPCIÓN (FECHA_ENTREGA), SERVICIO, CAMA y ASEGURADOR; filtro de visual: FACTURADOR dentro de una lista fija de 13 nombres.
- **Tabla facturación hospitalario**: Titulada «FACTURACION HOSPITALARIO»; mismas columnas; filtro de visual: FACTURADOR no vacío y fuera de una lista fija de 12 nombres.
- **Treemap por servicio**: Treemap «SERVICIO» con VALOR ESTIMADO por servicio de la cama.

## Reglas de negocio
- **Separación por facturador**: Ambulatorio y hospitalario no se separan por tipo de ingreso sino por listas de nombres de facturadores escritas en los filtros de cada tabla; si entra o sale un facturador hay que actualizarlas en Power BI.
- **Sin filtros de página**: A diferencia de TRAZABILIDAD, esta página no filtra AINESTADO ni PERFIL (confirmado en el PBIP)

## Observaciones
- **Listas que pueden no coincidir**: Las listas son de 13 y 12 nombres; un facturador que esté en una y no en la otra aparece en ambas tablas o en ninguna. Los ingresos sin facturador no aparecen en ninguna tabla.
- **Nombre del botón**: Se llega desde el botón TRAZABILIDAD de INICIO; la página llamada TRAZABILIDAD no tiene botón de entrada.

## Historial de cambios
- **2026-10-28 · v1**: Página documentada a partir del modelo y del informe.
