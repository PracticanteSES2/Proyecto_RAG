---
tablero: ASIGNACION DE CITAS
pagina: DETALLE ASIGNADAS
nombre_funcional: Listado de pacientes con solicitud de cita asignada
bloque: Histórico
tablas: [EN_ESPERA, Calendario]
actualizado: 2026-10-20
version: 1
---

# DETALLE ASIGNADAS

## Propósito
Lista, paciente por paciente, las solicitudes de la lista de espera que ya quedaron asignadas, con el médico, la especialidad y el asesor que gestionó. Se llega desde el botón DETALLE ASIGNADAS de INICIO; los datos se filtran por fecha de registro de la solicitud (bloque Histórico).

## Fuentes de datos
- **EN_ESPERA**: Solicitudes en estado asignada (CCEESTADO = 1) con datos de contacto, médico, especialidad y asesor.

## Indicadores
- **Consultas asignadas**: Solicitudes asignadas con los filtros aplicados. DISTINCTCOUNT(EN_ESPERA[OID_CITA]).

## Visuales
- **Filtros de la página**: Segmentadores de año, mes y día, ASESOR (EN_ESPERA[ASESOR]), ESPECIALIDAD, ASEGURADORA (EN_ESPERA[NOM_TERCERO]), clasificación MAESTROS y buscadores de texto por documento y nombre del paciente.
- **Tarjeta consultas asignadas**: Total de solicitudes asignadas.
- **Tabla de pacientes asignados**: Fecha de solicitud, documento, nombre, teléfono, MÉDICO (EN_ESPERA[GMENOMCOM]), especialidad y asesor.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Solo solicitudes asignadas**: Filtro de página CCEESTADO = 1.

## Observaciones
- **Documentación desactualizada**: La documentación titula esta página «DETALLE EN ESPERA» y describe columnas (días en espera, fecha de asignación, asesor de la cita, aseguradora y correo) que la tabla del PBIP no tiene. Prevalece el PBIP.
- **Datos personales**: La tabla muestra nombre, documento y teléfono del paciente; el RAG no debe transcribirlos.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
