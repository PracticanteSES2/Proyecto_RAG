---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: HOSPITALIZACION DIA
nombre_funcional: Oportunidad en la hospitalización del día
bloque: Día
tablas: [ESPERA_HOSPITALIZACION, HOSPITALIZACION_DIA]
actualizado: 2026-10-20
version: 1
---

# HOSPITALIZACION DIA

## Propósito
Muestra la oportunidad en la asignación de cama para los pacientes de urgencias que requieren hospitalización: pacientes que esperan cama, pacientes en proceso de remisión a otra institución y pacientes a los que se les asignó cama hoy. Todos los tiempos de esta página están en horas. Se llega desde el botón de hospitalización de RESUMEN_D.

## Fuentes de datos
- **ESPERA_HOSPITALIZACION**: Solicitudes de hospitalización activas de pacientes que siguen en una cama de urgencias; tabla en DirectQuery.
- **HOSPITALIZACION_DIA**: Solicitudes de hospitalización con cama asignada hoy; tabla en DirectQuery.
- **Remisiones**: Tabla PLANILLAUSUARIO.Con_RemisionMaestro_new; marca los ingresos en proceso de remisión y se cruza dentro de la consulta de ESPERA_HOSPITALIZACION.

## Indicadores
- **Tiempo en espera de hospitalización**: Horas desde la solicitud de hospitalización hasta el momento en que se consulta la página. Columna ESPERA_HOSPITALIZACION[TIEMPO_PARA_HOSPITALIZACION].
- **Tiempo para hospitalización**: Horas entre la solicitud de hospitalización y la asignación de cama. Columna HOSPITALIZACION_DIA[TIEMPO_PARA_HOSPITALIZACION].

## Visuales
- **Leyenda de oportunidad**: Texto con los rangos del semáforo de la página.
- **Tabla en espera hospitalización**: Pacientes con solicitud activa que no están en remisión, con documento, nombre y tiempo de espera en horas.
- **Tabla pacientes hospitalizados**: Pacientes con cama asignada hoy, con hora de solicitud, hora de asignación y tiempo de espera en horas.
- **Tabla pacientes en remisión**: Pacientes con solicitud activa en proceso de remisión; mismas columnas y semáforo que la tabla de espera.
- **Botón regresar**: Botón de la esquina superior izquierda que regresa a RESUMEN_D.

## Reglas de negocio
- **Semáforo de hospitalización**: Verde de 0 a 4 horas, amarillo de 5 a 6 y rojo de 7 o más.
- **Solicitud de hospitalización**: Registro de PLANILLAUSUARIO.DnSoliServicio_new con categoría de servicio 188 y servicio 1.
- **Solicitudes en espera**: Estados 1, 2 o 3, de pacientes cuya estancia actual está en una cama del subgrupo 16 (urgencias). La tabla no tiene filtro de fecha.
- **Paciente en remisión**: Ingreso con registro en la tabla de remisiones; se muestra aparte y no en la lista de espera.
- **Pacientes hospitalizados**: Solicitudes con cama asignada hoy (FecAsigCama igual a hoy) del área de urgencias.
- **Cálculo en horas**: Las horas se calculan con DATEDIFF(HOUR); 1 hora y 59 minutos se muestran como 1.

## Observaciones
- **Estados de la solicitud**: Los estados 1, 2 y 3 se interpretan como solicitudes activas. Por confirmar.
- **Hueco en el semáforo de hospitalizados**: En la tabla de pacientes hospitalizados el valor de 6 horas queda sin color.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
