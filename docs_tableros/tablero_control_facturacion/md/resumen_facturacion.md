---
tablero: TABLERO CONTROL FACTURACION
pagina: RESUMEN FACTURACION
nombre_funcional: Tiempos de gestión del proceso de facturación
bloque: Histórico
tablas: [FACTURACION PERFILES, CALENDARIO, DIM_TIPO_INGRESO]
actualizado: 2026-10-20
version: 1
---

# RESUMEN FACTURACION

## Propósito
Muestra el tiempo promedio de gestión de las cuentas en el proceso de facturación, día a día y separado en ambulatorio y hospitalario. Es la puerta a las páginas de cada perfil (auditorías, cuentas, radicación, enfermería, escaneo, facturación, archivo y auditores externos). Se llega desde el botón DETALLE FACTURACIÓN de INICIO o RESUMEN FACTURACION de PROCESO FACTURACION. Análisis histórico. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **FACTURACION PERFILES**: Una fila por cuenta y perfil con la primera fecha de recibe y la de entrega, responsables, paciente, entidad, tipo de ingreso, cama, servicio, área de servicio, estado de la factura, facturador y monto. Egresos desde el 1 de agosto de 2025 hasta hoy, ingresos con AINESTADO 0 o 1. FECHA es la fecha de egreso.

## Indicadores
- **Tiempo promedio de gestión de factura**: Promedio en horas de 'FACTURACION PERFILES'[TIEMPO] (horas entre recibe y entrega del perfil). Agregación: promedio de la columna.
- **Tiempo hospitalario**: Medida TIEMPO_FACTURACION_HOSPITALIZACION = CALCULATE(AVERAGE('FACTURACION PERFILES'[TIEMPO]), 'FACTURACION PERFILES'[TIPO INGRESO] = "HOSPITALARIO"). Unidad: horas.
- **Tiempo ambulatorio**: Igual al hospitalario con TIPO INGRESO = "AMBULATORIO" (TIEMPO_FACTURACION_AMBULATORIO). En la documentación aparece comentado; por confirmar.

## Visuales
- **Filtros**: Segmentadores AREA_SERVICIO, Año y Mes, y botones AMBULATORIO / HOSPITALARIO.
- **Tarjeta**: TIEMPO PROMEDIO GESTION FACTURA, en horas.
- **Gráfico de líneas diario**: Titulado «TIEMPO GESTION FACTURACION»; tiempo promedio de gestión por día.
- **Gráfico ambulatorio y hospitalario**: Titulado «TIEMPO FACTURACION AMBULATORIO Y HOSPITALARIO»; una línea por tipo de ingreso, por día.
- **Botones por perfil**: AUDITORIA MEDICAMENTOS, FACTURACION IMAGENES, CUENTAS, RADICACION DE CUENTAS, ESTACION DE ENFERMERIA, AUDITORIA PERTINENCIA, ESCANEO FOTOCOPIAS, FACTURACION, GESTION DE LA INFORMACION Y ARCHIVO y AUDITORES EXTERNOS; el botón de inicio vuelve a INICIO.

## Reglas de negocio
- **Todos los perfiles**: Esta página promedia el tiempo de todos los perfiles juntos; las páginas de perfil filtran uno solo.
- **Auditorías**: Para AUDITORIA PERTINENCIA y AUDITORIA MEDICAMENTOS el tiempo va de la asignación a la respuesta de la solicitud de auditoría.

## Observaciones
- **Filtro de estado**: Por confirmar si esta página filtra ESTADO_FACTURA = FACTURADA como las páginas de perfil.
- **Eje diario**: La documentación habla de comportamiento diario y la captura usa días; las páginas de perfil usan año y mes.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
