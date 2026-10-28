---
tablero: BRIEFING HOSPITALARIO
pagina: INICIO
nombre_funcional: Resumen diario de ocupación, flujo de pacientes y pendientes institucionales
bloque: Día
tablas: [CAMAS DISPONIBLES, SOLICITUD CAMAS, SEGUIMIENTO REMISIONES, DETALLE RECEPCION, PACIENTES X ASEGURADORA, EGRESOS PROBABLES, INGRESOS, EGRESOS, BOLETIN, NEDOCS, TRIAGES, REPS, MEDICAMENTOS DESABASTECIDOS, INTERCONSULTAS, CONVENIOS, AMBULATORIO_SS, IMAGENES_TOMADAS]
actualizado: 2026-10-28
version: 2
---

# INICIO

## Propósito
Página principal y única visible del tablero. Muestra en una sola vista el estado del día: ocupación por servicio, solicitudes de cama, remisiones, recepciones pendientes, pacientes por aseguradora, egresos probables, ingresos y egresos, casos del briefing, NEDOCS, triages y pendientes institucionales. Cada visual tiene un botón que abre su página de detalle.

## Fuentes de datos
- **CAMAS DISPONIBLES**: Estado actual de cada cama (consulta SELECT * FROM CAMAS_DISPONIBLES en el modelo); base de la ocupación.
- **Tablas de detalle**: Cada visual usa la misma tabla que su página de detalle; ver la página correspondiente.

## Indicadores
- **Porcentaje de ocupación**: Camas ocupadas sobre camas filtradas, en porcentaje. Medida %OCUPACION = DIVIDE(SUM('CAMAS DISPONIBLES'[OCUPADAS]), CamasFiltradas).
- **Camas por servicio**: Número de camas de la capacidad válida por servicio. Es la medida CamasFiltradas con el rótulo «Camas» en el visual.
- **Camas solicitadas**: Solicitudes de cama pendientes. DISTINCTCOUNT(SOLICITUD CAMAS[oid]).
- **Triages**: Número de triages. DISTINCTCOUNT(TRIAGES[OID_TRIAGE]).
- **Casos del briefing**: Número de casos abiertos. DISTINCTCOUNT(BOLETIN[OID_SOLICITUD]).
- **NEDOCS**: Valor de la escala de sobreocupación de urgencias. Medida NEDOCS[TotalN].

## Visuales
- **%OCUPACIÓN POR SERVICIO**: Columnas con el número de camas (medida CamasFiltradas) y línea con %OCUPACION por servicio; excluye el servicio CUIDADO ESPECIAL. Botón DETALLE GESTIÓN CAMAS, que lleva a la página GESTIÓN CAMAS.
- **CAMAS SOLICITADAS POR SERVICIO**: Columnas de solicitudes por servicio (SOLICITUD CAMAS[GDPNOMBRE]) separadas por sexo (HOMBRE, MUJER). Filtros estadooid 2 o 3 y sin cama asignada (camaoid vacío). Botón DETALLE SOLICITUD CAMAS, que lleva a la página SOLICITUD CAMAS.
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
- **PBIP actualizado**: El PBIP local ya trae los visuales de INICIO y las 21 páginas; donde la documentación original difiere del informe se documenta el informe.
- **Medida CAMAS**: La documentación original habla de una medida CAMAS; en el modelo no existe y el visual usa CamasFiltradas.
- **Periodo de camas solicitadas**: El visual del informe actual no filtra por fecha; muestra todas las solicitudes pendientes sin cama (la documentación original mencionaba una fecha relativa).
- **Ocupación al 100 %**: En la captura de INICIO varios servicios aparecen con 100,0 %; ver la observación sobre el numerador en GESTIÓN CAMAS.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
