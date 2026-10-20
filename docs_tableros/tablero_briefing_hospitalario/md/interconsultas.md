---
tablero: BRIEFING HOSPITALARIO
pagina: INTERCONSULTAS
nombre_funcional: Interconsultas de pacientes hospitalizados sin respuesta
bloque: Día
tablas: [INTERCONSULTAS]
actualizado: 2026-10-20
version: 1
---

# INTERCONSULTAS

## Propósito
Muestra las interconsultas solicitadas en los últimos 10 días para pacientes que siguen hospitalizados y que aún no tienen respuesta, con el tiempo de espera en horas y su distribución por servicio y especialidad. Sirve para priorizar la respuesta de las especialidades. Se llega desde el botón DETALLE de la tarjeta INTERCONSULTAS SIN RESPUESTA en INICIO.

## Fuentes de datos
- **INTERCONSULTAS**: Interconsultas de Dinámica (HCNINTERC) con folio y fecha de solicitud, respuesta (si existe), ingreso, paciente, especialidad (GEEDESCRI), cama, servicio y aseguradora. Solicitudes de los últimos 10 días.

## Indicadores
- **Interconsultas sin respuesta**: Interconsultas sin folio de respuesta. DISTINCTCOUNT(INTERCONSULTAS[OID_SOLICITUD]) con OID_RESPUESTA vacío.
- **Tiempo en espera**: Horas desde el folio de solicitud hasta la respuesta o, si no hay respuesta, hasta ahora. Columna TIEMPO_RESPUESTA_INTERCONSULTA; unidad horas.

## Visuales
- **Tarjeta INTERCONSULTAS SIN RESPUESTA**: Total según los filtros aplicados.
- **Segmentadores**: ESPECIALIDAD, SERVICIO y ASEGURADOR.
- **Tabla de interconsultas**: INGRESO, DOCUMENTO, PACIENTE, CAMA, SERVICIO, FECHA SOLICITUD, ESPECIALIDAD y TIEMPO EN ESPERA (HORAS). Filtro OID_RESPUESTA vacío.
- **Sin respuesta por servicio**: Barras con el número de interconsultas sin respuesta por servicio.
- **Sin respuesta por especialidad**: Barras con el número de interconsultas sin respuesta por especialidad.

## Reglas de negocio
- **Periodo**: Folio de solicitud con fecha entre hoy menos 10 días y hoy.
- **Pacientes hospitalizados**: Se excluyen los ingresos que ya tienen egreso.
- **Área de servicio**: Solo interconsultas del área de servicio 2 (GENARESER = 2).
- **Sin respuesta**: Todos los visuales filtran OID_RESPUESTA vacío.

## Observaciones
- **Área de servicio 2**: A qué área corresponde GENARESER = 2 no está documentado. Por confirmar.
- **Filtro sobrante**: La tarjeta tiene además un filtro sobre MEDICAMENTOS DESABASTECIDOS[OID_SOLICITUD], que parece un resto de otra página. Por confirmar si afecta el resultado.
- **Interconsultas antiguas**: Una interconsulta sin respuesta de más de 10 días sale del tablero aunque siga pendiente.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
