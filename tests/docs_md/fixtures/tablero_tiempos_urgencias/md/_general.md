---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: GENERAL
nombre_funcional: Tiempos de Urgencias: visión general del tablero
bloque: General
actualizado: 2026-10-20
version: 1
---

# GENERAL

## Propósito
Mide la oportunidad de la atención en el servicio de urgencias en cada etapa del recorrido del paciente: llegada y turno, triage, admisión, consulta médica, ingreso por enfermería, observación, laboratorio, imágenes, interconsultas, hospitalización y egreso.
Tiene dos bloques. El bloque Día muestra en tiempo real los pacientes en espera y los ya atendidos de cada etapa, con semáforo. El bloque Histórico muestra promedios y volúmenes por año y mes desde 2023 (desde 2024 en hospitalización y estancia) y mapas de calor por día de la semana y hora.
La página de inicio es RESUMEN_D; las demás páginas están ocultas en modo lectura y se abren con botones.

## Fuentes de datos
- **Servidor y base de datos**: SQL Server «LS-COBRA,1433\dinamica», base DWSES. Es la única conexión del modelo; todas las tablas se cargan con sentencias SQL nativas.
- **Bodega DWSES**: Tablas de la bodega con prefijos DIM_ y FACT_, por ejemplo DIM_TRIAGE, DIM_INGRESO, DIM_FOLIO, DIM_ORDEN_SALIDA y FACT_ESTANCIA.
- **Base DGEMPRES10**: Tablas operativas del sistema Dinámica Gerencial leídas por nombre de tres partes, por ejemplo ADNINGRESO, HCNTRIAGE, HCNFOLIO, HPNESTANC, HCNSOLEXA, HCNINTERC y CMNCITMED.
- **Base PLANILLAUSUARIO**: Aporta el digiturno (AdmisionTriage), las solicitudes de hospitalización (DnSoliServicio_new), las remisiones (Con_RemisionMaestro_new), el censo de urgencias (Et_ConsultaGrl) y el seguimiento de imágenes (segimagenes, segTOMADO, seginterpre).
- **Modelo compuesto**: El modelo semántico TABLERO TIEMPOS URGENCIAS (área de trabajo Gestion Clinica) combina tablas DirectQuery e Import.
- **Tablas del día en DirectQuery**: Se consultan en la base cada vez que se abre o actualiza la página: TRIAGES_DIA, EN ESPERA TRIAGE, ESPERA_ADMISION, CONSULTAS_DIA, EN_ESPERA_CONSULTA, PRIORITARIAS_DIA, EN ESPERA INGRESO, EN_OBSERVACION, PACIENTES_OBSERVADOS, HOSPITALIZACION_DIA, ESPERA_HOSPITALIZACION, EGRESOS_DIA, TIEMPO_EGRESO_DIA, ESPERA_EGRESO, INTERCONSULTA_DIA, LABORATORIOS_DIA e IMAGENES DIA.
- **Tablas del día en Import**: ADMISIONES_DIA e INGRESOS_DIA se importan; muestran el día de la última actualización del conjunto de datos.
- **Tablas históricas en Import**: OPORTUNIDAD_TRIAGE, CONSULTA_URGENCIAS, INICIO_TRAT_HIST, OBSERV_HIST, EXAMENES, IMAGENES, INTERCONSULTA, TIEMPO_PARA_EGRESO, HISTORICO_HOSP, TIEMPO_URGENCIAS, TIEMPO_HOSPI y CONSULTAS_PRIORITARIAS. Cambian solo al actualizar el conjunto de datos.
- **Calendario**: Tabla de fechas DAX, CALENDAR del 01/01/2023 a TODAY(). Alimenta los segmentadores Año, Mes y Día del bloque histórico.
- **Relaciones**: Solo las tablas históricas se relacionan con Calendario[FECHA], de varios a uno y con filtro en una dirección. Las tablas del día no tienen relaciones entre sí ni con Calendario.
- **Actualización programada**: La frecuencia de actualización del conjunto de datos en el servicio de Power BI no está en el PBIP. Por confirmar.

## Definiciones
- **Tiempo para triage**: Minutos entre la toma del turno en el digiturno (HCCFECTUR, hora de llegada) y el registro del triage (HCTFECTRI). En TRIAGES_DIA el paciente sin turno queda con 0 minutos; en OPORTUNIDAD_TRIAGE[MIN] queda vacío.
- **Tiempo entre triage y admisión**: Minutos entre el registro del triage (HCTFECTRI) y la admisión (AINFECING). Columnas ADMISIONES_DIA[TIEMPO_ESPERA], CONSULTAS_DIA[TRIAGE_ADM] y CONSULTA_URGENCIAS[MINUTOS_ADMISION].
- **Tiempo para consulta**: Minutos entre la admisión (AINFECING) y el primer folio de historia clínica del ingreso (HCFECFOL), que marca el inicio de la consulta. Columnas CONSULTAS_DIA[TIEMPO_ESPERA_CONS], CONSULTAS_DIA[TIEMPO_CONSULTA] y CONSULTA_URGENCIAS[MINUTOS_CONSULTA].
- **Tiempo para ingreso por enfermería**: Minutos entre el primer folio en urgencias (consulta) y el inicio de la estancia (HESFECING). En el bloque Día se llama ingreso por enfermería (INGRESOS_DIA) y en el Histórico inicio de tratamiento (INICIO_TRAT_HIST); es el mismo cálculo.
- **Tiempo en observación**: Minutos entre el inicio de la estancia (HESFECING) y el fin de la observación: la solicitud de hospitalización (SsFechaC) si no hay egreso, o el egreso (ADEFECSAL) si no hay solicitud. Si el paciente sigue en observación, se cuenta hasta la hora actual.
- **Tiempo para hospitalización del día**: Horas entre la solicitud de hospitalización (SsFechaC) y la asignación de cama (FecAsigCama). Columna HOSPITALIZACION_DIA[TIEMPO_PARA_HOSPITALIZACION]; para quien espera, ESPERA_HOSPITALIZACION cuenta hasta la hora actual.
- **Tiempo para hospitalización histórico**: Horas entre la admisión (AINFECING) y la asignación de cama (FecAsigCama). Columna HISTORICO_HOSP[TIEMPO_HOSPI]; no es el mismo intervalo que el del día.
- **Tiempo para el egreso**: Minutos entre el último folio de historia clínica del ingreso (HCFECFOL) y la orden de salida (SRAFECSAL). Columna TIEMPO_EGRESO_OK.
- **Tiempo de respuesta de interconsulta**: Tiempo entre el folio de solicitud y el folio de respuesta. En INTERCONSULTA_DIA está en horas y, sin respuesta, se cuenta hasta la hora actual; en INTERCONSULTA está en minutos y solo para interconsultas respondidas.
- **Tiempo de resultado de laboratorio**: Minutos entre la solicitud del examen (HCSFECSOL) y el resultado (HCRFECRES); si está pendiente, hasta la hora actual. Columna LABORATORIOS_DIA[TIEMPO_RESULTADO]; en el histórico, EXAMENES[TIEMPO_RESPUESTA] en minutos y solo con respuesta.
- **Tiempos de imágenes**: En IMAGENES DIA, en horas: toma (solicitud a toma, tmfecha), lectura (toma a lectura del radiólogo, FechaLecRadiologo) y resultado (solicitud a confirmación, HCRFECCONF). En el histórico IMAGENES el tiempo de respuesta está en minutos.
- **Tiempo de espera de consulta prioritaria**: Minutos entre la asignación de la cita (CCMFECASI) y la hora programada (CCMFECCIT). Mide la anticipación de la cita, no la espera real en sala.
- **Tiempo total en urgencias**: Horas entre la admisión (AINFECING) y la orden de salida (SRAFECSAL). Columna TIEMPO_URGENCIAS[TiempoMinutosSalidaUrgencias]; está en horas pese al nombre.
- **Tiempo en urgencias de hospitalizados**: Horas entre la admisión y el cierre de la solicitud de hospitalización (SsFechaFin). Columna TIEMPO_HOSPI[TIEMPO_HOSPI].
- **Tiempo para asignación de cama**: Minutos entre la admisión (FECHAINGRESO) y el inicio de la primera estancia (FECINGCAMA). Columna TIEMPO_PARA_EGRESO[TIEMPO_ASIG_CAMA].
- **Hora actual**: En las tablas de espera el tiempo se cuenta hasta GETDATE() del servidor, es decir, hasta el momento en que se consulta la página.
- **Cálculo con DATEDIFF**: Todos los tiempos usan DATEDIFF, que cuenta los límites de minuto u hora cruzados: 1 hora y 59 minutos medidos en horas dan 1.
- **Triage**: Valoración inicial que clasifica la urgencia del paciente en I, II, III, IV o V. Las variantes obstétricas llevan G (I-G emergencia, II-G urgencia médica, III-G urgencia, IV-G no urgente y V-G consulta externa obstétrica); el código M es paciente que llega fallecido (MUERTO).
- **Agrupación de códigos de triage**: IIIU se agrupa como III; IIP e IIS como II.
- **Digiturno**: Turno que el paciente toma al llegar (prefijo del módulo y número). Su hora es la hora de llegada u hora digiturno.
- **Admisión**: Registro administrativo del ingreso del paciente (ADNINGRESO o DIM_INGRESO, fecha AINFECING). También se llama admisión facturación.
- **Folio**: Registro de la historia clínica electrónica. El primer folio del ingreso marca el inicio de la consulta; el último folio es la referencia para medir el egreso.
- **Ingreso por enfermería**: Inicio de la estancia del paciente en una cama o ubicación del servicio (HPNESTANC o FACT_ESTANCIA, fecha HESFECING). En el histórico se llama inicio de tratamiento.
- **Observación**: Permanencia en el servicio después de la consulta, desde el inicio de la estancia hasta la solicitud de hospitalización o el egreso.
- **Solicitud de hospitalización**: Registro de PLANILLAUSUARIO.DnSoliServicio_new con categoría de servicio 188 y servicio 1. La asignación de cama es su fecha FecAsigCama.
- **Remisión**: Traslado del paciente a otra institución. Está en remisión si su ingreso tiene registro en PLANILLAUSUARIO.Con_RemisionMaestro_new.
- **Orden de salida**: Orden que autoriza la salida del paciente (DIM_ORDEN_SALIDA, fecha SRAFECSAL). Marca el egreso en los indicadores de egreso y de tiempo total en urgencias.
- **Interconsulta**: Solicitud de valoración a otra especialidad médica. La especialidad solicitada es la columna GEEDESCRI.
- **Consulta prioritaria**: Cita cuya actividad contiene la palabra PRIORITARIA (CMNCITMED). Según los rótulos del resumen del día atiende triage IV y V.
- **Tramo horario**: Hora del evento truncada a la hora en punto, en formato de 12 horas. Se usa en los mapas de calor.
- **Día de la semana**: Columnas DIA_SEMANA, DIA_SEMANA_CONSULTA y DIA_SEMANA_TRAT, numeradas de «1. LUNES» a «7. DOMINGO».
- **Semáforo**: Formato condicional de las tablas del día: verde (#48F579) dentro del tiempo esperado, amarillo (#E8D166) en alerta y rojo (#F65B40) fuera de tiempo. Los rangos de cada etapa están en su página.
- **Navegación del bloque Día**: RESUMEN_D lleva a TIEMPOS TRIAGE DIA, ADMISIONES DIA, CONSULTAS DIA, CONSULTAS PRIORITARIAS, INGRESOS DIA, PACIENTES EN OBSERVACION, INTERCONSULTAS DIA, LABORATORIOS, IMAGENES DIA, HOSPITALIZACION DIA y EGRESOS DIA; cada una regresa a RESUMEN_D.
- **Navegación del bloque Histórico**: RESUMEN_D lleva a RESUMEN y a MAPA DE CALOR TRIAGE. RESUMEN lleva a TIEMPO TRIAGE, TIEMPO TRIAGE-ADMISION, TIEMPO PARA CONSULTA, INICIO TRATAMIENTO HISTORICOS, OBSERVACIÓN HISTORICO, EXAMENES, IMAGENES, INTERCONSULTAS HISTORICO, TIEMPO EGRESO, TIEMPO HOSPI y TIEMPO ESTANCIA; las páginas de tiempo enlazan su mapa de calor.

## Reglas de negocio
- **Exclusión del triage UA**: Todas las consultas que leen triages excluyen el código UA.
- **Área de urgencias**: El área de servicio 2 (GENARESER = 2) identifica urgencias; filtra folios, interconsultas, exámenes y solicitudes de hospitalización. EXAMENES incluye además el área 42.
- **Unidad de urgencias**: El subgrupo de camas 16 (HPNSUBGRU = 16) corresponde a URGENCIAS. Los indicadores de egreso filtran además SUBGRUPO = URGENCIAS.
- **Egresos válidos**: Un tiempo para el egreso es válido si es mayor que 0 y hasta 720 minutos (12 horas). Los demás tienen VALIDADOR = -1 y se excluyen de promedios y conteos.
- **Órdenes de salida**: Solo cuentan órdenes no anuladas (SRAORDANU = 0) de ingresos con AINURGCON = 0.
- **Admisiones anuladas**: CONSULTAS_DIA excluye ingresos con estado AINESTADO = '2'; CONSULTA_URGENCIAS excluye los estados '2' y '4'.
- **Clasificaciones que esperan admisión o consulta**: ESPERA_ADMISION y EN_ESPERA_CONSULTA solo toman triages no confirmados (HCTCONFIR = 0) con clasificación de identificador interno 2, 7, 9, 16, 17, 18 o 19.
- **Primera solicitud por ingreso**: En laboratorios, imágenes y exámenes se conserva una sola solicitud por ingreso, la primera según la fecha de respuesta, con las pendientes primero.
- **Ventanas de las tablas del día**: La mayoría trae solo la fecha actual del servidor. Interconsultas, laboratorios e imágenes traen los últimos 3 días; EN_OBSERVACION, los ingresos de los últimos 10 días; EN ESPERA TRIAGE, ESPERA_ADMISION, ESPERA_EGRESO y ESPERA_HOSPITALIZACION no tienen límite de fecha.
- **Ventanas de las tablas históricas**: Desde el 01/01/2023, salvo HISTORICO_HOSP, TIEMPO_HOSPI y TIEMPO_URGENCIAS (desde el 01/01/2024) y CONSULTAS_PRIORITARIAS (desde el 01/01/2022).
- **Agregaciones implícitas**: Los indicadores son agregaciones de columnas en cada visual (promedio, suma, conteo o conteo distinto); cada página indica la expresión DAX equivalente.
- **Filtro de fechas del histórico**: Los segmentadores Año, Mes y Día usan la jerarquía de Calendario[FECHA]. Cada tabla histórica define su FECHA según su propio evento, indicado en cada página.
- **Alcance de los filtros del día**: Un filtro sobre una tabla del día solo afecta a los visuales que usan esa misma tabla.

## Observaciones
- **Medida %ATENDIDO**: SUM(INTERCONSULTA[RESPUESTAS]) / SUM(INTERCONSULTA[SOLICITUDES]). Porcentaje de interconsultas respondidas; se usa en INTERCONSULTAS HISTORICO.
- **Medida %ATENCION**: SUM(EXAMENES[CANT_RESPUESTAS]) / SUM(EXAMENES[CANT_EXAMENES]). Siempre da 100 % porque EXAMENES solo carga solicitudes con respuesta; sin uso en visuales.
- **Medida %MEDIDO**: SUM(TIEMPO_PARA_EGRESO[EGRESOS_CORR_URG]) / SUM(TIEMPO_PARA_EGRESO[EGRESOS_URG]). Porcentaje de egresos de urgencias con tiempo válido; sin uso en visuales.
- **Medida %MEDIDO_DIA**: Igual que %MEDIDO sobre TIEMPO_EGRESO_DIA (órdenes de salida de hoy); sin uso en visuales.
- **Medida PRUEBA**: (SUM(CONSULTA_URGENCIAS[MINUTOS_ADMISION]) + SUM(CONSULTA_URGENCIAS[MINUTOS_CONSULTA])) / COUNT(CONSULTA_URGENCIAS[DOCUMENTO]). Medida de prueba sin uso; se sugiere eliminarla.
- **Páginas con el mismo nombre**: Hay dos páginas llamadas INTERCONSULTAS en Power BI; aquí se documentan como INTERCONSULTAS DIA e INTERCONSULTAS HISTORICO. Se recomienda renombrarlas.
- **Páginas sin botón de llegada**: RESUMEN DIA y TIEMPO ASIGNACIÓN CAMAS no tienen ningún botón que lleve a ellas; solo se ven en modo edición.
- **Columna con nombre engañoso**: TIEMPO_URGENCIAS[TiempoMinutosSalidaUrgencias] está en horas. Solo tiene valor si facturación recibió la historia antes de la orden de salida y vale 0 si enfermería la entregó después. Por confirmar la regla.
- **Tablas del día en Import**: ADMISIONES_DIA e INGRESOS_DIA no se actualizan en tiempo real como las demás tablas del día. Por confirmar si es intencional.
- **Filtros sin efecto**: Varios visuales filtran columnas de tablas sin relación con la del visual, por ejemplo la tabla de egresos filtrada por CONSULTAS_DIA[HORA_CONSULTA]. Esos filtros no cambian el resultado; se señalan en cada página.
- **Reglas de color heredadas**: Varias tablas tienen reglas de color sobre columnas que no están en el visual; esas reglas no se aplican.
- **Huecos en los semáforos**: En algunas tablas los rangos no son continuos y ciertos valores quedan sin color; se indican en cada página.
- **Fechas guardadas como texto**: En CONSULTA_URGENCIAS (LLEGADA_PORTERO, FECHA_TRIAGE, FECHA_FOLIO, FECHA_FOLIO2) y OPORTUNIDAD_TRIAGE (LLEGADA_PORTERO) las fechas son texto dd/mm/aaaa hh:mm:ss. Las columnas DAX calculadas sobre ellas dependen de la configuración regional.
- **Tabla sin uso**: CONSULTAS_PRIORITARIAS (histórica) no se usa en ningún visual; la página CONSULTAS PRIORITARIAS usa PRIORITARIAS_DIA.
- **Botón Azul**: La documentación versión 1 describe un botón de medicina prepagada priorizada que no existe en el PBIP. Por confirmar si la versión publicada es más reciente.
- **Fecha de referencia**: Las tablas del día usan GETDATE() del servidor SQL y Calendario usa TODAY() de DAX, que en el servicio usa hora UTC. Entre las 7:00 p. m. y la medianoche (hora de Colombia) el Calendario puede incluir el día siguiente. Por confirmar.
- **Datos personales**: Las tablas del día muestran nombre y documento de los pacientes. Toda captura debe anonimizarse antes de compartirse fuera del área.
- **Diferencias con la versión 1**: En la versión 1 las sentencias SQL de triage y de admisiones del día estaban intercambiadas y varias no coincidían con el modelo; esta documentación sigue el PBIP.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
