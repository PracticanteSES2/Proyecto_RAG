---
tablero: DEMANDA INSATISFECHA
pagina: SOLICITUD CAMAS
nombre_funcional: Solicitudes de cama no asignadas
bloque: Histórico
tablas: [SOLICITUD DE CAMAS]
actualizado: 2026-10-28
version: 2
---

# SOLICITUD CAMAS

## Propósito
Analiza las solicitudes de cama que no se asignaron: total, promedio mensual, evolución por mes y distribución por servicio y por asegurador. Es el componente de hospitalización de la demanda insatisfecha; se llega desde el botón HOSPITALIZACIÓN (camas) de CONSOLIDADO. Análisis histórico. Página oculta en Power BI (solo CONSOLIDADO es visible).

## Fuentes de datos
- **SOLICITUD DE CAMAS**: Solicitudes de servicio de cama (DNSOLISERVICIO_NEW, categoría OidCatServicio = 188) creadas desde el 1 de enero de 2025 hasta hoy. Trae servicio solicitante, estado, fechas de creación, fin y asignación de cama, sexo, paciente, asegurador, fecha de egreso (ADEFECSAL) y la cama. FECHA es la fecha de creación de la solicitud.

## Indicadores
- **Solicitudes no asignadas**: Suma de la columna DEMANDA_INS, que vale 1 cuando la solicitud tiene estado 4, no tiene fecha de asignación ni cama y el paciente ya egresó. Es el valor que entra a CONSOLIDADO. DAX: SUM('SOLICITUD DE CAMAS'[DEMANDA_INS])
- **Total solicitudes no asignadas (medida)**: Medida TOTAL_SOLICITUD_CAMAS: solicitudes distintas con egreso registrado, sin fecha de asignación de cama y con estado distinto de 4. DAX: CALCULATE(DISTINCTCOUNT('SOLICITUD DE CAMAS'[Oid]), NOT(ISBLANK('SOLICITUD DE CAMAS'[ADEFECSAL])), ISBLANK('SOLICITUD DE CAMAS'[FecAsigCama]), 'SOLICITUD DE CAMAS'[EstadoOid] <> 4).
- **Promedio mensual**: Medida DEMANDA_INS_PM. DAX: DIVIDE(SUM('SOLICITUD DE CAMAS'[DEMANDA_INS]), MONTH(TODAY())).

## Visuales
- **Tarjetas**: NO ASIGNADAS y PROMEDIO MENSUAL.
- **Gráfico de columnas por mes**: Titulado «NO ASIGNADAS por Mes»; solicitudes no asignadas por mes.
- **Gráfico circular por servicio**: Titulado «NO ASIGNADAS por SERVICIO»; participación por servicio solicitante (por ejemplo urgencias, quirófanos, UCI adultos).
- **Gráfico de barras por asegurador**: Titulado «NO ASIGNADAS por ASEGURADOR».
- **Filtros**: Segmentadores «Date Año» y «Date Mes» (CALENDARIO[Date]), «SERVICIO» (SOLICITUD DE CAMAS[GDPNOMBRE]) y «ASEGURADOR» (SOLICITUD DE CAMAS[aseguradora]), y botón de inicio que vuelve a CONSOLIDADO.

## Reglas de negocio
- **Solicitud no asignada**: DEMANDA_INS exige estado 4, sin fecha de asignación de cama, sin cama y con fecha de egreso del paciente; la medida TOTAL_SOLICITUD_CAMAS usa en cambio estado distinto de 4.
- **Sexo**: GPASEXPAC 1 se muestra como HOMBRE y 2 como MUJER.
- **Filtro de página**: Solo cuentan las solicitudes de los servicios QUIROFANOS, SALA AZUL 3 PISO, UCI ADULTOS, URGENCIAS y CUIDADO INTERMEDIO SUR (SOLICITUD DE CAMAS[GDPNOMBRE])

## Observaciones
- **Promedio sin filtro de año**: DEMANDA_INS_PM no se limita al año en curso, a diferencia de los promedios de las otras páginas.
- **Unión de subgrupo**: La consulta une HPNSUBGRU por el OID del ingreso igual al servicio solicitante (d.OID = a.serviciooid); el nombre de subgrupo (HSUNOMBRE) puede ser incorrecto. Por confirmar.
- **Dos reglas de cama**: DEMANDA_INS (estado igual a 4) y TOTAL_SOLICITUD_CAMAS (estado distinto de 4) usan estados opuestos; una de las dos puede estar mal. Por confirmar el significado del estado 4.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
