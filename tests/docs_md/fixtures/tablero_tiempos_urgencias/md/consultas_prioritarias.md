---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: CONSULTAS PRIORITARIAS
nombre_funcional: Consultas prioritarias del día
bloque: Día
tablas: [PRIORITARIAS_DIA]
actualizado: 2026-10-20
version: 1
---

# CONSULTAS PRIORITARIAS

## Propósito
Muestra las citas de consulta prioritaria del día: cuántas hay asignadas, cómo se reparten por médico y por hora, y el detalle de cada cita con la hora de asignación y la hora programada. Según los rótulos del resumen del día, esta consulta atiende triage IV y V. Se llega desde el botón de consulta prioritaria de RESUMEN_D y el botón superior izquierdo regresa a RESUMEN_D.

## Fuentes de datos
- **PRIORITARIAS_DIA**: Citas con actividad PRIORITARIA programadas para hoy; tabla en DirectQuery.

## Indicadores
- **Consultas asignadas**: Número de citas prioritarias de hoy no anuladas. DISTINCTCOUNT(PRIORITARIAS_DIA[OID]).
- **Tiempo de espera de consulta prioritaria**: Minutos entre la asignación de la cita (CCMFECASI) y la hora programada (CCMFECCIT). Columna PRIORITARIAS_DIA[TIEMPO_ESPERA_PRIORITARIA].

## Visuales
- **Matriz citas por médico y tramo horario**: Filas TRAMO HORARIO (hora programada), columnas nombre del médico y valor número de citas, DISTINCTCOUNT(PRIORITARIAS_DIA[OID]).
- **Tarjeta consultas asignadas**: Conteo distinto de citas del día no anuladas.
- **Segmentador de médico**: Filtra la página por PRIORITARIAS_DIA[NOMBRE_MEDICO].
- **Tabla consultas prioritarias**: Columnas DOCUMENTO, PACIENTE, HORA ASIGNACION, HORA CONSULTA (hora programada), MÉDICO y TIEMPO ESPERA. Sin semáforo efectivo; su filtro sobre EN_OBSERVACION no tiene efecto.

## Reglas de negocio
- **Semáforo de citas por hora**: En la matriz, rojo para 0 o 1 cita por hora y médico, amarillo para 2 y verde para 3; con 4 o más la celda queda sin color.
- **Cita prioritaria**: Cita cuya actividad (CMNTIPACT.CMANOMBRE) contiene la palabra PRIORITARIA.
- **Citas anuladas**: Filtro de página que excluye el estado ANULADO. Los estados son REGISTRADO (0), ANULADO (1) y CONFIRMADO (2).
- **Documentos excluidos**: Se excluyen las citas con CCMPACDOC entre 30 y 39.

## Observaciones
- **Interpretación del semáforo de citas**: El significado de los colores por número de citas está por confirmar con el área.
- **Espera real no medida**: El tiempo mide la anticipación de la cita, no la espera real; la fecha de cumplimiento (CCMFECCUM) está en la tabla pero no se usa. Por confirmar.
- **Valores de CCMPACDOC**: El significado de los valores 30 a 39 excluidos está por confirmar.
- **Reglas de color sin efecto**: Las reglas de color de la tabla de detalle se refieren a TRIAGES_DIA[MIN], que no está en la tabla.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
