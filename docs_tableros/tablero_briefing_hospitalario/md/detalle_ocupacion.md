---
tablero: BRIEFING HOSPITALARIO
pagina: DETALLE OCUPACIÓN
nombre_funcional: Pacientes hospitalizados con días de estancia y semáforo de estancia prolongada
bloque: Día
tablas: [PACIENTES X ASEGURADORA, AUDITORIA_CONCURRENTE]
actualizado: 2026-10-28
version: 2
---

# DETALLE OCUPACIÓN

## Propósito
Lista los pacientes que ocupan cama en este momento con su servicio, aseguradora, plan y días de estancia, coloreados según la estancia. Incluye el conteo por rango de estancia, la distribución por servicio, el filtro de pacientes con cirugía pendiente hace más de 48 horas y el seguimiento de auditoría concurrente. Se llega desde el botón DETALLE OCUPACIÓN del visual PACIENTES por ASEGURADORA en INICIO.

## Fuentes de datos
- **PACIENTES X ASEGURADORA**: Camas ocupadas (HCAESTADO = 2) con ingreso, paciente, plan de beneficios, servicio, aseguradora y días de estancia. Se une con la programación de cirugía para traer la especialidad y las horas desde la solicitud de cirugía.
- **AUDITORIA_CONCURRENTE**: Notas de seguimiento de auditoría concurrente por paciente con fecha, texto y responsable. Consulta de origen por confirmar.

## Indicadores
- **Total pacientes**: Pacientes hospitalizados ocupando cama. DISTINCTCOUNT(PACIENTES X ASEGURADORA[ADNINGRESO]).
- **Días de estancia**: Días calendario entre la fecha de ingreso (AINFECING) y hoy. Columna DIAS_ESTANCIA.
- **Horas de cirugía pendiente**: Horas desde el registro de la solicitud de cirugía hasta ahora. Columna CantidadHoras (CANTIDAD HORAS CIRUGÍA).
- **Pacientes por rango de estancia**: Pacientes por cada rango de TIEMPO_ESTANCIA. DISTINCTCOUNT(ADNINGRESO).

## Visuales
- **Tarjeta TOTAL PACIENTES**: Total según los filtros aplicados.
- **Leyenda de colores**: Texto con los rangos «6 a 8 Días», «Entre 9 y 14 Días» y «15 Días o más» y su color.
- **Botón CIRUGÍAS MAYOR A 48 HORAS**: Segmentador FILTRO_QX que deja solo pacientes con solicitud de cirugía de más de 48 horas.
- **Segmentadores**: SERVICIO y ASEGURADORA.
- **Tabla de pacientes**: CEDULA, PACIENTE, CAMA, SERVICIO, ASEGURADORA, PLAN DE BENEFICIOS, CANTIDAD HORAS CIRUGÍA y ESPECIALIDAD CIRUGÍA; cada fila se colorea según ColorFila.
- **Tabla TIEMPO DE ESTANCIA**: Cantidad de pacientes por rango (5 DÍAS O MENOS, 6 A 8 DÍAS, 9 A 14 DÍAS, 15 DÍAS O MÁS) con total.
- **Pacientes por servicio**: Anillo «HSUNOMBRE» con el conteo de ADNINGRESO y el porcentaje de pacientes por servicio.
- **Tabla de seguimiento**: DOCUMENTO PACIENTE, PACIENTE, FECHA, SEGUIMIENTO y RESPONSABLE de la auditoría concurrente.

## Reglas de negocio
- **Semáforo de estancia (ColorFila)**: Amarillo de 4 a 8 días, naranja de 9 a 14 días y rojo de 15 días o más; menos de 4 días queda sin color.
- **Rangos de estancia (TIEMPO_ESTANCIA)**: 5 DÍAS O MENOS (menos de 6), 6 A 8 DÍAS, 9 A 14 DÍAS y 15 DÍAS O MÁS.
- **Cirugía mayor a 48 horas**: Solicitud de cirugía de tipo 2 o 5, registrada hace 48 horas o más y con estado distinto de 13 y 8; FILTRO_QX vale «CIRUGÍAS MAYOR A 48 HORAS» cuando hay especialidad.
- **Solo camas ocupadas**: La consulta toma camas con HCAESTADO = 2 y con ingreso asociado.

## Observaciones
- **Semáforo y leyenda no coinciden**: ColorFila pinta de amarillo desde 4 días, pero la leyenda y la tabla de rangos empiezan en 6 días; los pacientes con 4 y 5 días salen amarillos y se cuentan en «5 DÍAS O MENOS». Por confirmar cuál es el umbral correcto.
- **Pacientes por aseguradora en INICIO**: El visual de INICIO que trae a esta página usa la misma tabla; su cálculo exacto (porcentaje por TERNOMCOM) está por confirmar.
- **Versión de marzo**: La versión de marzo de 2026 de la documentación no traía la tabla de rangos de estancia.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
