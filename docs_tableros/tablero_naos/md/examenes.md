---
tablero: TABLERO NAOS
pagina: EXAMENES
nombre_funcional: Exámenes y estudios diagnósticos pendientes por paciente
bloque: Día
tablas: [PACIENTES, EXAMENES, ResumenExamenes]
actualizado: 2026-10-28
version: 2
---

# EXAMENES

## Propósito
Muestra los pacientes del tablero NAOS que tienen exámenes o estudios diagnósticos pendientes, con la lista consolidada de exámenes por ingreso, para gestionarlos a tiempo. Es seguimiento del estado actual. Se llega con el botón EXÁMENES PENDIENTES de LISTADO.

## Fuentes de datos
- **EXAMENES**: Vista EXAMENES_NAOS cargada completa (DirectQuery); una fila por examen de un ingreso, con ingreso, documento, paciente, servicio, cama, código y descripción del examen y su estado.
- **ResumenExamenes**: Tabla calculada desde EXAMENES; une por ingreso, paciente, cama y servicio los nombres (SIPDESCUP) de los exámenes con ESTADO_EXAMEN igual a PENDIENTE, separados por coma.
- **PACIENTES**: Vista TABLERO_NAOS; relacionada con ResumenExamenes por PACIENTES[AINCONSEC], filtra la tabla por ingreso.

## Indicadores
- **Exámenes pendientes por ingreso**: Lista de los nombres de exámenes pendientes de cada ingreso, separados por coma. Unidad: texto. Columna ResumenExamenes[ExamenesPendientes].

## Visuales
- **Botón de inicio**: Icono de casa que regresa a LISTADO.
- **Segmentación de ResumenExamenes[HSUNOMBRE]**: Lista de SERVICIO para filtrar los ingresos.
- **Segmentación de PACIENTES[AINCONSEC]**: Lista de INGRESO para buscar un ingreso.
- **Tabla INGRESO**: Columnas INGRESO (ResumenExamenes[AINCONSEC]), PACIENTE (ResumenExamenes[GPANOMCOM]) y EXAMENES PENDIENTES (ResumenExamenes[ExamenesPendientes]); una fila por ingreso con todos sus exámenes pendientes (laboratorio, imágenes, terapias y procedimientos) en una sola celda.
- **Filtro de la página**: Filtra PACIENTES[HSUNOMBRE] de la página.

## Reglas de negocio
- **Examen pendiente**: Un examen cuenta como pendiente cuando EXAMENES[ESTADO_EXAMEN] vale PENDIENTE; los demás estados no entran en la lista.
- **Un registro por ingreso**: Los exámenes pendientes de un mismo ingreso se concatenan en una sola celda.

## Observaciones
- **Consulta de EXAMENES_NAOS**: La lógica de la vista y los valores posibles de ESTADO_EXAMEN además de PENDIENTE no están documentados. Por confirmar.
- **Filas sin pendientes**: ResumenExamenes tiene una fila por ingreso aunque no tenga exámenes pendientes; en ese caso ExamenesPendientes queda vacío. Por confirmar si la tabla los oculta.
- **Sin filtro de tipo de paciente**: A diferencia de las demás páginas, no tiene filtro TIPO PACIENTE.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
