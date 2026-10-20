---
tablero: TABLERO NAOS
pagina: EXAMENES PENDIENTES
nombre_funcional: Exámenes y estudios diagnósticos pendientes por paciente
bloque: Día
tablas: [PACIENTES]
actualizado: 2026-10-20
version: 1
---

# EXAMENES PENDIENTES

## Propósito
Muestra los pacientes del tablero NAOS que tienen exámenes o estudios diagnósticos pendientes, con la lista consolidada de exámenes por ingreso, para gestionarlos a tiempo. Es seguimiento del estado actual. Se llega con el botón EXÁMENES PENDIENTES de LISTADO.

## Fuentes de datos
- **Exámenes pendientes**: Origen no documentado; por confirmar si viene de la vista TABLERO_NAOS (tabla PACIENTES) u otra consulta.

## Indicadores
- **Exámenes pendientes por ingreso**: Lista de los nombres de exámenes pendientes de cada ingreso, separados por coma. Unidad: texto.

## Visuales
- **Botón de inicio**: Icono de casa que regresa a LISTADO.
- **Filtros de segmentación**: Listas de SERVICIO e INGRESO.
- **Tabla exámenes pendientes**: Columnas INGRESO, PACIENTE y EXAMENES PENDIENTES; una fila por ingreso con todos sus exámenes (laboratorio, imágenes, terapias y procedimientos) en una sola celda.

## Reglas de negocio
- **Un registro por ingreso**: Los exámenes pendientes de un mismo ingreso se concatenan en una sola celda.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar; la documentación la llama «NAOS- EXAMENES PENDIENTES» y el botón «EXÁMENES PENDIENTES».
- **Sin consulta documentada**: La documentación no trae la consulta ni la tabla de esta página. Por confirmar.
- **Criterio de pendiente**: No se documenta cuándo un examen se considera pendiente (solicitado sin resultado, sin toma de muestra u otro). Por confirmar.
- **Sin filtro de tipo de paciente**: A diferencia de las demás páginas, no tiene filtro TIPO PACIENTE.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
