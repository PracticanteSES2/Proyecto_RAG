---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: RESUMEN DIA
nombre_funcional: Resumen día, versión alterna (página oculta)
bloque: Día
tablas: [TRIAGES_DIA, CONSULTAS_DIA, TIEMPO_EGRESO_DIA, HOSPITALIZACION_DIA]
actualizado: 2026-10-28
version: 2
---

# RESUMEN DIA

## Propósito
Versión alterna del resumen del día, titulada «TIEMPOS DE ATENCIÓN EN URGENCIAS». Tiene el mismo diagrama con botones y los mismos indicadores que RESUMEN_D, más el tiempo entre triage y admisión. Ningún botón lleva a esta página; solo se ve en modo edición y parece una versión anterior de RESUMEN_D.

## Fuentes de datos
- **TRIAGES_DIA**: Triages registrados hoy, excepto el código UA; tabla en DirectQuery.
- **CONSULTAS_DIA**: Triages de hoy con su admisión y su primer folio de historia clínica; tabla en DirectQuery.
- **TIEMPO_EGRESO_DIA**: Órdenes de salida de hoy de todas las unidades; tabla en DirectQuery.
- **HOSPITALIZACION_DIA**: Solicitudes de hospitalización del área de urgencias con cama asignada hoy; tabla en DirectQuery.

## Indicadores
- **Tiempo entre triage y admisión facturación**: Minutos entre el registro del triage y la admisión, para los triages de hoy. AVERAGE(CONSULTAS_DIA[TRIAGE_ADM]); solo aparece en esta página.
- **Indicadores comunes con RESUMEN_D**: Tiempo promedio para triage, para consulta urgencias, para el egreso y para hospitalización se calculan igual que en RESUMEN_D.

## Visuales
- **Títulos del diagrama**: Título «TIEMPOS DE ATENCIÓN EN URGENCIAS» y rótulos «TRIAGE I, II Y III» junto al botón de consultas y «TRIAGE IV Y V» junto al botón de consultas prioritarias.
- **Tarjetas y medidores del día**: Tiempo para triage, tiempo entre triage y admisión facturación y tiempo para consulta en minutos; medidor de egreso en minutos y medidor de hospitalización en horas.
- **Botones de navegación**: Llevan a TIEMPOS TRIAGE DIA, ADMISIONES DIA, CONSULTAS DIA, CONSULTAS PRIORITARIAS, INGRESOS DIA, PACIENTES EN OBSERVACION, INTERCONSULTAS DIA, LABORATORIOS, IMAGENES DIA, HOSPITALIZACION DIA, EGRESOS DIA, MAPA DE CALOR TRIAGE y RESUMEN.
- **Nombres de campos**: Nombres de los campos en el informe: tarjeta «Última fecha: FECHA»; tarjeta «TIEMPO PROMEDIO PARA CONSULTA URGENCIAS»; medidor «TIEMPO PROMEDIO PARA HOSPITALIZACIÓN»; medidor «TIEMPO PROMEDIO PARA EL EGRESO».

## Reglas de negocio
- **Filtros de los indicadores**: Los indicadores tienen los mismos filtros que en RESUMEN_D, incluidos los que no tienen efecto.

## Observaciones
- **Vigencia de la página**: Por confirmar si RESUMEN DIA debe seguir en el informe. Si se conserva, el indicador de triage a admisión podría pasarse a RESUMEN_D.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
