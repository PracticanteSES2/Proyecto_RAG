---
tablero: ASIGNACION DE CITAS
pagina: DETALLE CITAS ASIGNADAS DÍA
nombre_funcional: Detalle de citas de un médico (obtención de detalles)
bloque: Histórico
tablas: [ASIGNADAS_ACTIVIDAD, AGENDA_ESPECIALISTAS]
actualizado: 2026-10-28
version: 2
---

# DETALLE CITAS ASIGNADAS DÍA

## Propósito
Página de obtención de detalles (drillthrough) por médico: al profundizar desde un médico lista sus pacientes citados con especialidad y actividad. Tiene un botón de regreso a DISPONIBILIDAD X ESPECIALIDAD. No está en la documentación del propietario; se describe solo con el PBIP (bloque Histórico).

## Fuentes de datos
- **ASIGNADAS_ACTIVIDAD**: Tabla de citas con médico, paciente, especialidad y actividad. No existe en el modelo semántico actual.

## Visuales
- **Tabla de citas del médico**: Columnas ASIGNADAS_ACTIVIDAD[Nombre_Medico], ASIGNADAS_ACTIVIDAD[GPANOMCOM] (nombre del paciente), ASIGNADAS_ACTIVIDAD[PACNUMDOC] (documento), ASIGNADAS_ACTIVIDAD[Especialidad] y ASIGNADAS_ACTIVIDAD[ACTIVIDAD].
- **Botón de regreso**: Vuelve a DISPONIBILIDAD X ESPECIALIDAD.

## Reglas de negocio
- **Obtención de detalles por médico**: La página recibe el filtro AGENDA_ESPECIALISTAS[Nombre_Medico] del visual de origen.
- **Bloqueos excluidos**: La tabla excluye filas sin paciente y las de agenda bloqueada (paciente «BLOQUEADO PARA»).

## Observaciones
- **Página rota**: ASIGNADAS_ACTIVIDAD y la columna AGENDA_ESPECIALISTAS[Nombre_Medico] no existen en el modelo (la columna actual es GMENOMCOM), por lo que la tabla y el filtro no funcionan. Por confirmar si la página está en desuso.
- **Nombre de página en Power BI**: Nombre tomado del PBIP; la documentación no la menciona.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir del PBIP; la página no está en la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
