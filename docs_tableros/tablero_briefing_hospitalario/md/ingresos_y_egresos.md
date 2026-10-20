---
tablero: BRIEFING HOSPITALARIO
pagina: INGRESOS Y EGRESOS
nombre_funcional: Ingresos y egresos hospitalarios del último día por servicio y EPS
bloque: Día
tablas: [INGRESOS, EGRESOS, SERV, TercerosRelacionados]
actualizado: 2026-10-20
version: 1
---

# INGRESOS Y EGRESOS

## Propósito
Muestra los pacientes que ingresaron y egresaron de hospitalización en el último corte diario, con el detalle por servicio y EPS y la participación de cada EPS. Sirve para analizar el flujo de pacientes y planear la capacidad. Se llega desde el botón INGRESOS Y EGRESOS de INICIO y tiene un botón hacia ATENCIONES POR ASEGURADOR.

## Fuentes de datos
- **INGRESOS**: Ingresos hospitalarios de Dinámica entre las 7:00 de ayer y las 7:00 de hoy, con paciente, plan, tipo, estado, origen y causa del ingreso, y el primer servicio y cama asignados.
- **EGRESOS**: Vista CD_EGRESOS de PLANILLAUSUARIO con servicio, cama, ingreso, fecha de ingreso y fecha de salida del servicio, unida con el nombre del paciente.
- **SERV y TercerosRelacionados**: Catálogos de servicios y de EPS usados por los segmentadores.

## Indicadores
- **Ingresos**: Ingresos hospitalarios del periodo. DISTINCTCOUNT(INGRESOS[CONSECUTIVO]).
- **Egresos**: Egresos del periodo sin hospitalización parcial. DISTINCTCOUNT(EGRESOS[INGRESO]).
- **Participación por EPS**: Porcentaje de ingresos (o egresos) de cada EPS sobre el total. DISTINCTCOUNT del ingreso dividido por el mismo conteo sin filtro de EPS.

## Visuales
- **Tarjetas**: INGRESOS y EGRESOS.
- **Segmentadores**: SERVICIO (SERV[HSUNOMBRE]) y EPS (TercerosRelacionados[nombre_tercero]).
- **Botón ATENCIONES POR SERVICIO**: Abre la página ATENCIONES POR ASEGURADOR.
- **Tabla INGRESOS**: SERVICIO, CAMA, PACIENTE, EPS y FECHA INGRESO.
- **Tabla EGRESOS**: SERVICIO, CAMA, PACIENTE, EPS, FECHA INGRESO y FECHA SALIDA.
- **Ingresos por EPS**: Barras con el porcentaje de ingresos por EPS.
- **Egresos por EPS**: Barras con el porcentaje de egresos por EPS.

## Reglas de negocio
- **Ventana de ingresos**: AINFECING desde las 7:00 de ayer hasta antes de las 7:00 de hoy.
- **Ingresos válidos**: Solo ingresos hospitalarios (AINTIPING = 2), no anulados (AINESTADO distinto de 2), con AIINGCORCU distinto de 1 y servicio distinto del subgrupo 12.
- **Servicio del ingreso**: Se toma una estancia del ingreso cuya cama no es del subgrupo 16; la consulta usa TOP 1 sin orden, así que no garantiza que sea la primera.
- **Hospitalización parcial**: Filtro de página que excluye HOSPITALIZACION PARCIAL de los egresos.
- **Servicios del segmentador**: Excluye servicios vacíos, los BLOQUEAR y CAMAS MAL CREADAS EN EL SISTEMA.

## Observaciones
- **Periodo de egresos**: El periodo de la vista CD_EGRESOS no está documentado. Por confirmar si usa la misma ventana de 7:00 a 7:00.
- **Consulta de egresos incompleta**: En la consulta transcrita el cierre de FORMAT quedó dentro de un comentario, por lo que no es ejecutable tal cual. Revisar contra la consulta real.
- **Subgrupos 12 y 16 y AIINGCORCU**: Qué servicios son los subgrupos 12 y 16 y qué marca AIINGCORCU está por confirmar.
- **Versión de marzo**: La versión de marzo de 2026 describía un selector de rango (Año, Mes, Semestre o Ayer) y una página INGRESOS Y EGRESOS POR SERVICIO que comparaba ayer con el rango; la versión vigente no los incluye. Por confirmar si esa página sigue existiendo.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
