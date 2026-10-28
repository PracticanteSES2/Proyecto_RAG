---
tablero: BRIEFING HOSPITALARIO
pagina: INICIO
nombre_funcional: Resumen diario de ocupación, flujo de pacientes y pendientes institucionales
bloque: Día
tablas: [CAMAS DISPONIBLES, SOLICITUD CAMAS, SEGUIMIENTO REMISIONES, DETALLE RECEPCION, PACIENTES X ASEGURADORA, EGRESOS PROBABLES, INGRESOS, EGRESOS, BOLETIN, NEDOCS, TRIAGES, REPS, MEDICAMENTOS DESABASTECIDOS, INTERCONSULTAS, CONVENIOS, AMBULATORIO_SS, IMAGENES_TOMADAS]
actualizado: 2026-10-20
version: 1
---

# INICIO

## Propósito
Página principal y única visible del tablero. Muestra en una sola vista el estado del día: ocupación por servicio, solicitudes de cama, remisiones, recepciones pendientes, pacientes por aseguradora, egresos probables, ingresos y egresos, casos del briefing, NEDOCS, triages y pendientes institucionales. Cada visual tiene un botón que abre su página de detalle.

## Fuentes de datos
- **CAMAS DISPONIBLES**: Estado actual de cada cama (consulta CAMAS_DISPONIBLES3); base de la ocupación.
- **Tablas de detalle**: Cada visual usa la misma tabla que su página de detalle; ver la página correspondiente.

## Indicadores
- **Porcentaje de ocupación**: Camas ocupadas sobre camas filtradas, en porcentaje. Medida %OCUPACION = DIVIDE(SUM('CAMAS DISPONIBLES'[OCUPADAS]), CamasFiltradas).
- **Camas por servicio**: Número de camas de la capacidad válida por servicio. Medida CAMAS; su DAX está por confirmar.
- **Camas solicitadas**: Solicitudes de cama pendientes. DISTINCTCOUNT(SOLICITUD CAMAS[oid]).
- **Triages**: Número de triages. DISTINCTCOUNT(TRIAGES[OID_TRIAGE]).
- **Casos del briefing**: Número de casos abiertos. DISTINCTCOUNT(BOLETIN[OID_SOLICITUD]).
- **NEDOCS**: Valor de la escala de sobreocupación de urgencias. Medida NEDOCS[TotalN].

## Visuales
- **%OCUPACIÓN POR SERVICIO**: Columnas con el número de camas (medida CAMAS) y línea con %OCUPACION por servicio. Botón DETALLE GESTIÓN CAMAS.
- **CAMAS SOLICITADAS POR SERVICIO**: Columnas de solicitudes por servicio (SOLICITUD CAMAS[GDPNOMBRE]) separadas por sexo (HOMBRE, MUJER). Filtros estadooid 2 o 3, sin cama asignada y fecha de solicitud relativa. Botón DETALLE SOLICITUD CAMAS.
- **REMISIONES por SERVICIO**: Anillo con remisiones en trámite por servicio, en número y porcentaje. Botón SEGUIMIENTO REMISIÓN.
- **PENDIENTES RECEPCIÓN por SERVICIO**: Anillo con pacientes pendientes de recepción por servicio. Botón SEGUIMIENTO RECEPCIÓN.
- **PACIENTES por ASEGURADORA**: Barras con el porcentaje de pacientes hospitalizados por aseguradora y tarjeta TOTAL PACIENTES. Botón DETALLE OCUPACIÓN.
- **EGRESOS PROBABLES por SERVICIO**: Anillo con egresos probables por servicio. Botón EGRESOS PROBABLES.
- **INGRESOS y EGRESOS por SERVICIO**: Columnas agrupadas con ingresos y egresos por servicio. Botón INGRESOS Y EGRESOS.
- **CASOS por SERVICIO**: Anillo con casos del briefing por servicio que los reporta (BOLETIN[SERVICIO]). Botón DETALLE BRIEFING.
- **Tarjeta NEDOCS**: Valor de NEDOCS con su clasificación como título (por ejemplo «Criticamente Sobreocupado»). Botón DETALLE NEDOCS.
- **TRIAGES por CLASIFICACIÓN**: Anillo con triages por clasificación (TRIAGES[DESCRI_TRIGE]). Excluye clasificaciones que contienen OBSTETRICA o MUERTO. Botón DETALLE URGENCIAS.
- **Tarjeta REPS**: Total de capacidad instalada REPS. Botón DETALLE hacia REPS.
- **Tarjeta MEDICAMENTOS E INSUMOS DESABASTECIDOS**: Número de casos de desabastecimiento abiertos. Botón DETALLE.
- **Tarjeta INTERCONSULTAS SIN RESPUESTA**: Número de interconsultas sin respuesta. Botón DETALLE.
- **CONVENIOS por TIPO**: Anillo con número y porcentaje de convenios por tipo. Botón DETALLE.
- **CONSULTAS PRÓXIMA SEMANA**: Matriz de citas por tramo horario (filas) y fecha (columnas) con mapa de calor. COUNT(AMBULATORIO_SS[CITA]). Botón DETALLE.
- **IMAGENES TOMADAS POR TRAMO HORARIO**: Matriz de imágenes tomadas por tramo horario y fecha con mapa de calor. Botón DETALLE.
- **PACIENTES EMERGENCIA MOVIMIENTO TELURICO**: Torta de pacientes por observación (EPS, ADRES, derivado a consulta prioritaria, fallecido) con tarjeta TOTAL DE PACIENTES. Botón DETALLE.

## Reglas de negocio
- **Servicios de la página**: Filtro de página por SERVICIOS[HSUNOMBRE]: ATENCION DOMICILIARIA, CUARTO PISO NORTE, CUARTO PISO SUR, CUIDADO INTERMEDIO NORTE, CUIDADO INTERMEDIO SUR, HOSPITALIZACION NEONATOS, OBSTETRICIA, QUINTO PISO NORTE, QUINTO PISO SUR, SALA AZUL 3 PISO, SEXTO PISO, UNIDAD DE CUIDADO INTENSIVO, URGENCIAS y URGENCIAS 2 PISO.
- **Camas de la página**: Filtros de página: MOSTRAR distinto de NO MOSTRAR, MOSTRAR_6TO distinto de 0 y código de cama que no contiene 321 ni 322.
- **Título de la tarjeta NEDOCS**: La clasificación que se muestra sobre el valor sigue los rangos definidos en DETALLE NEDOCS.

## Observaciones
- **Visuales no presentes en el PBIP local**: El PBIP local de INICIO solo trae CAMAS SOLICITADAS, CASOS, TRIAGES, CONSULTAS PRÓXIMA SEMANA y dos botones; el resto se documenta desde la documentación del propietario.
- **Medida CAMAS**: La documentación del propietario usa la medida CAMAS en %OCUPACIÓN POR SERVICIO; su DAX no está documentado. Por confirmar si es igual a CamasFiltradas.
- **Periodo de camas solicitadas**: El visual usa un filtro de fecha relativa sobre SOLICITUD CAMAS[ssfechac]; el periodo exacto está por confirmar.
- **Ocupación al 100 %**: En la captura de INICIO varios servicios aparecen con 100,0 %; ver la observación sobre el numerador en DETALLE GESTIÓN CAMAS.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
