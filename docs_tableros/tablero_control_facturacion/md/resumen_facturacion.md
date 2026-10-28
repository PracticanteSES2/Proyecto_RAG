---
tablero: TABLERO CONTROL FACTURACION
pagina: RESUMEN FACTURACION
nombre_funcional: Tiempos de gestión del proceso de facturación
bloque: Histórico
tablas: [FACTURACION PERFILES, CALENDARIO, DIM_TIPO_INGRESO]
actualizado: 2026-10-28
version: 2
---

# RESUMEN FACTURACION

## Propósito
Muestra el tiempo promedio de gestión de las cuentas en el proceso de facturación, día a día y separado en ambulatorio y hospitalario. Es la puerta a las páginas de cada perfil (auditorías, cuentas, radicación, enfermería, escaneo, facturación, archivo y auditores externos). Se llega desde el botón DETALLE FACTURACIÓN de INICIO o RESUMEN FACTURACION de PROCESO FACTURACION. Análisis histórico. Página oculta en Power BI.

## Fuentes de datos
- **FACTURACION PERFILES**: Una fila por cuenta y perfil con la primera fecha de recibe y la de entrega, responsables, paciente, entidad, tipo de ingreso, cama, servicio, área de servicio, estado de la factura, facturador y monto. Egresos desde el 1 de agosto de 2025 hasta hoy, ingresos con AINESTADO 0 o 1. FECHA es la fecha de egreso.

## Indicadores
- **Tiempo promedio de gestión de factura**: Promedio en horas de 'FACTURACION PERFILES'[TIEMPO] (horas entre recibe y entrega del perfil). Agregación: promedio de la columna.
- **Tiempo hospitalario**: Medida TIEMPO_FACTURACION_HOSPITALIZACION = CALCULATE(AVERAGE('FACTURACION PERFILES'[TIEMPO]), 'FACTURACION PERFILES'[TIPO INGRESO] = "HOSPITALARIO"). Unidad: horas.
- **Tiempo ambulatorio**: Medida TIEMPO_FACTURACION_AMBULATORIO: promedio de TIEMPO de las cuentas con TIPO INGRESO = AMBULATORIO. Unidad: horas.

## Visuales
- **Filtros**: Segmentadores «AREA_SERVICIO» (ULT_GESTION[AREA_SERVICIO]), «Date Año» y «Date Mes» (CALENDARIO[Date]) y «TIPO_INGRESO» (DIM_TIPO_INGRESO[TIPO_INGRESO], botones AMBULATORIO / HOSPITALARIO)
- **Tarjeta**: TIEMPO PROMEDIO GESTION FACTURA: promedio de 'FACTURACION PERFILES'[TIEMPO], en horas.
- **Gráfico de tiempo de gestión**: Gráfico de áreas titulado «TIEMPO GESTION FACTURACION»; promedio de TIEMPO por fecha del calendario (jerarquía de fechas; la documentación lo muestra por día)
- **Gráfico ambulatorio y hospitalario**: Gráfico de áreas titulado «TIEMPO FACTURACION AMBULATORIO Y HOSPITALARIO» con una serie por tipo de ingreso (AMBULATORIO y HOSPITALARIO), por fecha del calendario.
- **Botones por perfil**: Botones AUDITORIA MEDICAMENTOS, FACTURACION IMAGENES, CUENTAS, RADICACION DE CUENTAS, ESTACION DE ENFERMERIA, AUDITORIA PERTINENCIA, ESCANEO FOTOCOPIAS, FACTURACION y GESTION DE LA INFORMACION Y ARCHIVO llevan a su página; el botón AUDITORES EXTERNOS no tiene destino en el PBIP; el botón de inicio vuelve a INICIO.

## Reglas de negocio
- **Todos los perfiles**: Esta página promedia el tiempo de todos los perfiles juntos; las páginas de perfil filtran uno solo.
- **Auditorías**: Para AUDITORIA PERTINENCIA y AUDITORIA MEDICAMENTOS el tiempo va de la asignación a la respuesta de la solicitud de auditoría.
- **Sin filtros de página**: La página no filtra perfil ni estado de la factura (confirmado en el PBIP): promedia el tiempo de todos los perfiles, de cuentas facturadas o no.

## Observaciones
- **Segmentador de área**: El segmentador AREA_SERVICIO es de ULT_GESTION, que no se relaciona con FACTURACION PERFILES; probablemente no filtre las medidas de la página. Por confirmar.
- **Horas por día**: FACTURACION PERFILES convierte FECHA_RECIBE y FECHA_ENTREGA a fecha sin hora, por lo que el tiempo de gestión en horas es siempre un múltiplo de 24 (equivale a días por 24)

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
