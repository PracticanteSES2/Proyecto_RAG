---
tablero: ASIGNACION DE CITAS
pagina: DISPONIBILIDAD X ESPECIALIDAD
nombre_funcional: Versión anterior de la disponibilidad de agenda por especialidad
bloque: Histórico
tablas: [AGENDA_ESPECIALISTAS, ESPECIALIDADES, EN_ESPERA, CITAS_ASIGNADAS, Calendario]
actualizado: 2026-10-28
version: 2
---

# DISPONIBILIDAD X ESPECIALIDAD

## Propósito
Página oculta que parece una versión anterior de DISPO X ESPECIALIDAD: compara por especialidad y médico la agenda, las citas y las solicitudes en espera. Ningún botón de INICIO la abre; solo se llega de regreso desde DETALLE CITAS ASIGNADAS DÍA. No está en la documentación del propietario; se describe solo con el PBIP (bloque Histórico).

## Fuentes de datos
- **AGENDA_ESPECIALISTAS**: Bloques de agenda por médico y día con cupos y citas.
- **EN_ESPERA**: Solicitudes en espera por especialidad.
- **CITAS_ASIGNADAS**: Citas para el gráfico de anillo.
- **ESPECIALIDADES**: Nombre de la especialidad.

## Indicadores
- **Agenda total**: SUM(AGENDA_ESPECIALISTAS[Disponibilidad_Dia]).
- **Cantidad citas**: SUM(AGENDA_ESPECIALISTAS[CANTIDAD_CITAS]).
- **Citas disponibles**: SUM(AGENDA_ESPECIALISTAS[Citas_Restantes]).
- **Citas en espera**: SUM(EN_ESPERA[PENDIENTES]).

## Visuales
- **Filtros de la página**: Segmentadores «Date Año», «Date Mes» y «Date Día», rotulados año, mes y día (usan la fecha completa de Calendario) y de especialidad.
- **Tabla de disponibilidad**: Matriz con especialidad y MEDICO; columnas AGENDA TOTAL, CITAS EN ESPERA, CANTIDAD CITAS y CITAS DISPONIBLES.
- **Anillo de agenda**: Solicitudes en espera, citas asignadas (DISTINCTCOUNT de CITAS_ASIGNADAS[OID_CITA]) y una columna de agenda disponible en minutos.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Color de citas en espera**: Degradado de verde (mínimo) a rojo (máximo) sobre CITAS EN ESPERA.
- **Citas del anillo**: Solo citas en estado 0 o 2 con fecha de cita de hoy en adelante (filtro de fecha relativa).

## Observaciones
- **Campo inexistente**: El anillo usa AGENDA_ESPECIALISTAS[AGENDA DISPONIBLE(MINUTOS)], que no existe en el modelo; el visual muestra error. Por confirmar si la página está en desuso.
- **Nombre de página en Power BI**: Nombre tomado del PBIP; la documentación no la menciona.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir del PBIP; la página no está en la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
