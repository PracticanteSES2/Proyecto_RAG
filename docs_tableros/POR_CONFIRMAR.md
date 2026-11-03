# Preguntas pendientes para el propietario de los tableros

Lista de lo que la documentación (`docs_tableros/<grupo>/md/`) todavía marca «Por confirmar» y que no se pudo resolver con el modelo publicado (`data/model_metadata`), el PBIP (`tableros/`), la documentación .docx ni los catálogos. Las preguntas son cerradas: basta con responder sí/no, elegir una opción o dar el dato.

Cómo leerla:

- Va primero lo que cambia una cifra que ve el usuario (tarjetas e indicadores); después columnas, visuales y reglas; al final páginas y mantenimiento.
- «Consulta X» remite a la consulta DAX de `tools/consultas_por_confirmar.json` cuyo resultado (ejecutado el 2026-11-03) ya se usó para documentar lo que los datos muestran; la pregunta queda porque la respuesta depende de la intención del dueño.
- «Dónde» señala la entrada del .md que se actualiza con la respuesta.
- Para ver el detalle de cada mención: `python -X utf8 tools/por_confirmar.py [--grupo <grupo>]`.

## Estado

- Menciones «Por confirmar» en los .md: 644 → 466 (en los diccionarios: 156 → 85). Corte: 2026-11-03.
- Preguntas para el propietario: 145, de ellas 44 con impacto en tarjetas o indicadores.
- Consultas DAX de solo lectura: 53 en `tools/consultas_por_confirmar.json`; se ejecutaron 52 contra el modelo publicado el 2026-11-03 y sus conclusiones ya están en los .md. La referencia-01 no se ejecutó porque agrupa por una columna que puede traer nombres de personas.

| Tablero | Menciones que quedan | Preguntas |
|---|---|---|
| TABLERO DE ATENCIONES INSTITUCIONALES | 157 | 28 | 
| TABLERO PERFIL DE MORBILIDAD | 47 | 6 | 
| TABLERO FINANCIERA | 42 | 12 | 
| BRIEFING HOSPITALARIO | 37 | 17 | 
| TABLERO TIEMPOS URGENCIAS | 34 | 14 | 
| TABLERO REFERENCIA | 29 | 5 | 
| TABLERO CONTROL FACTURACION | 28 | 11 | 
| DEMANDA INSATISFECHA | 17 | 7 | 
| ASIGNACION DE CITAS | 16 | 11 | 
| TABLERO CVC | 11 | 6 | 
| TABLERO EPS | 11 | 5 | 
| TABLERO NAOS | 10 | 6 | 
| TABLERO LAVANDERIA | 9 | 2 | 
| TABLERO FARMACIA | 8 | 6 | 
| TABLERO RECEPCION TECNICA | 7 | 5 | 
| TABLERO ANTIBIOTICOS | 3 | 3 | 

## Una petición para varios tableros: PBIP completos

Varios PBIP de `tableros/` llegan sin la definición de los visuales (carpetas `visuals` vacías) o no existen. Con un PBIP exportado de nuevo desde Power BI Desktop se resuelven sin el propietario la mayoría de las «Medida por confirmar», los filtros de página y la navegación. ¿Puede exportar y dejar en `tableros/` el PBIP completo de estos tableros?

- **TABLERO DE ATENCIONES INSTITUCIONALES**: El PBIP del tablero solo trae los visuales de INDICADORES (en parte), CONSULTAS PRIORITARIAS, LABORATORIO PATOLOGICO y DETALLE ESPECIALIDADES; las demás páginas llegan con las carpetas de visuales vacías. ¿Puede exportar de nuevo el PBIP completo desde Power BI Desktop? Con él se confirma la medida de cada tarjeta y gráfico marcada «Medida por confirmar» (unas 40 entradas en 30 páginas).
- **TABLERO CVC**: ¿Puede compartir el PBIP con los visuales de la página CVC? El actual trae la página vacía, así que no se sabe qué medidas y columnas alimentan tarjetas, gráfico y tabla.
- **TABLERO FINANCIERA**: ¿Puede compartir el PBIP (o las consultas de Power Query) del TABLERO FINANCIERA? Sin él no se documentan las consultas SQL de origen, la granularidad de las tablas, los filtros Top N ni las etiquetas de los visuales.
- **TABLERO LAVANDERIA**: ¿Puede compartir el PBIP con los visuales de la página? El actual no trae visuales, así que los totales (suma de Peso) y el porcentaje de participación se documentaron desde la documentación del propietario.
- **TABLERO PERFIL DE MORBILIDAD**: ¿Puede compartir el PBIP completo del TABLERO PERFIL DE MORBILIDAD? El local trae las páginas sin visuales; sin él no se documentan los visuales ni las tablas (AMBULATORIO, PERIOPERATORIA o MATRIZ 2024) de las 7 páginas ocultas ambulatorias y perioperatorias.
- **TABLERO REFERENCIA**: ¿Puede compartir el PBIP completo de TABLERO REFERENCIA? El local no trae visuales: faltan los filtros reales (la documentación dice EPS, rango de edad y fechas; la captura, EPS/ESTADO, DOCUMENTO y fechas), los visuales de SEGUIMIENTOS REMISION y de qué tabla toma cada visual de DETALLE REMISION.

## TABLERO DE ATENCIONES INSTITUCIONALES

### Afecta una tarjeta o un indicador visible

1. **ATE-1** Oportunidad de cirugía ambulatoria (medidor de CIRUGÍAS y de ESPECIALIDADES CIRUGIA): ¿es el promedio de OPORTUNIDAD CIRUGIA[OPORTUNIDAD], en días, entre Planeada (o Trámite Clínico/ADM) y Paciente en Salida? — dónde: `cirugias.md / especialidades_cirugia.md › Indicadores › Oportunidad de cirugía ambulatoria; _diccionario.md › Tablas › OPORTUNIDAD CIRUGIA`.
2. **ATE-2** Promedio de estancia de INDICADORES: la medida PROMEDIO_ESTANCIA que cita la documentación ya no existe; [PROMEDIO_ESTANCIA_TOTAL] y [PROMEDIO_ESTANCIA_TOTAL1] dan el mismo valor (en decenas) y las demás medidas de estancia dan unidades, ninguna cerca de los 118 a 148 de la captura. ¿Qué medida usa el gráfico y en qué unidad (días por egreso u otra)? — consulta atenciones-08; dónde: `indicadores.md › Indicadores › Promedio de estancia; Observaciones › Unidad del promedio de estancia; _diccionario.md › [ESTANCIA_TOTAL]`.
3. **ATE-3** La tarjeta CAPACIDAD INSTALADA muestra 308 camas, pero ni las listas fijas del modelo ([NUM_CAM_EGRESOS] da 248 y [NUMERO_CAMAS] 280) ni las tablas de camas dan 308. ¿De dónde sale el 308 y quién actualiza esas listas de camas por servicio? — consulta atenciones-07; dónde: `indicadores.md › Indicadores › Capacidad instalada; Observaciones › Capacidad instalada sin cuadrar; _diccionario.md › Observaciones › Listas fijas de camas`.
4. **ATE-4** Giro cama: ¿debe contar solo egresos PUERTA o TRASLADO (como dice la documentación y hacen [GIRO_CAMA_ANO_ACTUAL]/[GIRO_CAMA_ANO_ANTERIOR]) o todos los ingresos con egreso del año (como hace hoy [GIRO_CAMA1], el del gráfico)? — dónde: `indicadores.md › Reglas de negocio › Egresos para giro cama; _diccionario.md › Observaciones › Giro cama y tipo de egreso`.
5. **ATE-5** ¿Las constantes de CONSULTAS_AMBULATORIAS son las metas de oportunidad en días: CONSULTA_PRA = 15 (primera vez), CONTROL = 20 (control) y GENERAL = 20 (general)? — dónde: `_diccionario.md › Columnas calculadas › CONSULTAS_AMBULATORIAS[CONSULTA_PRA], [CONTROL], [GENERAL]`.
6. **ATE-6** Las medidas [PRIORITARIAS_*] y [TIEMPO_OPORTUNIDAD_PRIORITARIAS_*] usan columnas que ya no existen (OID_TRIAGE, TIEMPO_PARA_CONSULTA) y CONSULTAS OBSTETRICAS filtra por TIPO_TRIAGE, que tampoco existe. ¿Se corrigen o se retiran? ¿La oportunidad de consulta (OPORTUNIDAD URGENCIAS y OPORTUNIDAD CONSULTA OBSTÉTRICA) se mide con tiempo_consulta o con TIEMPO_CONSULTA_CALCULADA? — dónde: `_diccionario.md › Observaciones › Medidas con columnas que no existen; oportunidad_urgencias.md › Indicadores › Promedio del gráfico; oportunidad_consulta_obstetrica.md › Indicadores y Reglas › Tiempo para consulta; Observaciones › Tarjeta vacía`.
7. **ATE-7** Cirugías: ESTADO ACTUAL va de Planeada a Paciente En Salida, con Paciente Cancelado como estado aparte (lista completa en el diccionario). ¿Qué estados cuentan como «pendiente» y es «Paciente Cancelado» el de «cancelada»? ¿CANCELACIONES usa CIRUGIAS_PENDIENTES u OPORTUNIDAD CIRUGIA y filtra por ESTADO ACTUAL o por la fecha de «Paciente Cancelado»? — consulta atenciones-09; dónde: `pendientes.md › Indicadores › Cirugías pendientes; Observaciones › Definición de pendiente; cancelaciones.md`.

### Columnas, visuales y reglas

8. **ATE-8** ¿Qué significa el estado de ingreso AINESTADO 4 (se excluye junto con el 2, ANULADO) y la marca AIINGCORCU = 1? — dónde: `_general.md › Reglas de negocio › Ingresos excluidos; oportunidad_urgencias.md › Reglas de negocio › Ingresos excluidos; _diccionario.md › Observaciones › Pendientes de negocio`.
9. **ATE-9** ¿Qué significan los estados 1, 2 y 3 de los resultados de patología (los únicos que entran en LABORATORIO PATOLOGICO)? — dónde: `laboratorio_patologico.md › Reglas de negocio › Estados válidos`.
10. **ATE-10** ¿Cuáles son las especialidades con identificador 1, 2, 3, 4, 6, 8, 51, 65, 88, 90 y 129 que CONSULTAS PRIORITARIAS excluye? — dónde: `consultas_prioritarias.md › Reglas de negocio › Especialidades excluidas`.
11. **ATE-11** % OCUPACIONAL: la columna de estado de CAMAS HABILITADAS mezcla OCUPADA, DESOCUPADA, MANTENIMIENTO y BLOQUEADA con los códigos 1, 2 y 5. ¿Qué significan 1, 2 y 5? La regla «CRIT en el nombre ⇒ CUIDADO CRÍTICO OBSTETRICO» rotula también al servicio UNIDAD DE CUIDADO CRITICO: ¿debe aplicarse solo a la unidad obstétrica? — consulta atenciones-11; dónde: `porcentaje_ocupacional.md › Observaciones › Estados numéricos; Regla CRIT amplia`.
12. **ATE-12** Vistas obstétricas: las clasificaciones obstétricas son exactamente las terminadas en «-G» (I-G a V-G). ¿TRIAGES OBSTÉTRICOS, OPORTUNIDAD TRIAGE OBSTÉTRICO, CONSULTAS OBSTÉTRICAS, OBSERVACIONES OBSTÉTRICAS y el botón de obstetricia de TRIAGE filtran por esas clasificaciones? ¿Qué regla de triage I está vigente? — consulta atenciones-05; dónde: `triages_obstetricos.md, oportunidad_triage_obstetrico.md, consultas_obstetricas.md, observaciones_obstetricas.md › Filtro obstétrico; triage.md › Reglas › Vista obstetricia`.
13. **ATE-13** En HOSPITALIZACIÓN PARCIAL y SES EN TU HOGAR, ¿el segmentador DIAGNÓSTICO usa CIE10, CMD o GRD? — dónde: `hospitalizacion_parcial.md / ses_en_tu_hogar.md › Observaciones › Campo del filtro de diagnóstico`.
14. **ATE-14** Sin año seleccionado, las tarjetas de promedio y proyección usan el año cerrado anterior y algunas tarjetas de total suman todos los años (SES EN TU HOGAR, CIRUGÍAS, CONSULTAS AMBULATORIAS, HOSPITALIZACIÓN PARCIAL). ¿Es el comportamiento deseado? — dónde: `cirugias.md › Proyección sin año seleccionado; ses_en_tu_hogar.md › Tarjeta ATENCIONES; consultas_ambulatorias.md › Proyección con bases distintas; Precedencia en Promedio_Dinamico; hospitalizacion_parcial.md › Medidas no documentadas`.
15. **ATE-15** Varios visuales muestran otro periodo que las tarjetas (torta de TRIAGE, mapa y anillo de TIPO LABORATORIO PATOLOGICO, mapa de árbol de ESPECIALIDAD IMAGENES, gráficos de QUIMIOTERAPIA y RADIOTERAPIA, torta de TRIAGES OBSTÉTRICOS). ¿Deben seguir al segmentador de año? — dónde: `triage.md › Torta con otro periodo; tipo_laboratorio_patologico.md › Mapa y anillo; especialidad_imagenes.md › Mapa de árbol sin año; quimioterapia.md / radioterapia.md › Años del gráfico; triages_obstetricos.md › Total distinto a la torta`.
16. **ATE-16** ¿El total de PARTOS excluye todos los tipos que no son parto (ABORTO, IVE, IVE EXTRA INSTITUCIONAL e IVE EXTRAINSTITUCIONAL)? ¿Cuáles son los visuales rotos de ABORTOS y PARTOS? — dónde: `partos.md › Observaciones › Tipos que no son parto; Visuales rotos; abortos.md › Observaciones › Visuales rotos`.
17. **ATE-17** REFERENCIA Y CONTRARREFERENCIA y MOTIVOS DE NO ACEPTACIÓN: los datos confirman que una solicitud con varias causas ocupa varias filas. ¿Las tarjetas deben contar solicitudes distintas (sí/no)? ¿MOTIVOS filtra solo el estado No Aceptado y la causa mayoritaria es de verdad un motivo de no aceptación? — consulta atenciones-10; dónde: `referencia_y_contrarreferencia.md › Indicadores › Solicitudes; Posibles duplicados; motivos_de_no_aceptacion.md`.
18. **ATE-18** UNIDAD CARDIONEUROVASCULAR: ¿el gráfico muestra la cantidad mensual ([CANT_ATENCIONESUCAR]) o el promedio ([PROM_ATENCIONESUCAR])? ¿Qué versión de las medidas está vigente? ¿El código CUPS de 6 dígitos que se ve en ESPECIALIDADES CARDIOVASCULAR es correcto? — dónde: `unidad_cardioneurovascular.md › Observaciones; especialidades_cardiovascular.md › Código CUPS sospechoso`.
19. **ATE-19** CONSULTAS SIN TRIAGE: ¿el gráfico cuenta todos los ingresos de urgencias o solo los sin triage? ATENCIONES PEDIÁTRICAS TRIAGE: ¿gráfico y torta filtran menores de edad? LABORATORIO: ¿qué medida usa el gráfico y cuál la tabla (no cuadran)? — dónde: `consultas_sin_triage.md › Gráfico frente a porcentaje; atenciones_pediatricas_triage.md › Valores que no cuadran; laboratorio.md › Gráfico y tabla no cuadran`.
20. **ATE-20** CONSULTAS PRIORITARIAS: ¿por qué las dos tarjetas salen «(En blanco)»? (la tarjeta del PBIR usa [PROMEDIO_MENSUAL]). — dónde: `consultas_prioritarias.md › Tarjetas en blanco`.
21. **ATE-21** ¿Hay meta o semáforo (en minutos) para la oportunidad del triage y de la consulta de urgencias? De los dos documentos de OPORTUNIDAD TRIAGE, ¿cuál está vigente? — dónde: `oportunidad_triage.md › Observaciones › Sin meta; Dos documentos; oportunidad_urgencias.md › Sin meta`.

### Páginas, navegación y mantenimiento

22. **ATE-22** Las relaciones de CIRUGIAS[OID] con ASEGURADORAS, CAMAS y UNIDAD no unen ninguna fila (ningún OID coincide), y la de SERVICIO con ASEGURADORAS (uno a uno) une dos catálogos distintos. ¿Se eliminan? (Las de IMAGENES_* con ASEGURADORAS sí coinciden.) — consulta atenciones-04; dónde: `_diccionario.md › Relaciones de CIRUGIAS y SERVICIO`.
23. **ATE-23** ¿El área GENARESER = 108 de QUIMIOTERAPIA es la misma que GASCODIGO = 108 de UNIDAD_CARDIOVASCULAR? — dónde: `_diccionario.md › Observaciones › Código de área 108`.
24. **ATE-24** Páginas de la documentación que no aparecen con ese nombre en el PBIP: ATENCIONES PEDIÁTRICAS CONSULTAS, ATENCIONES PEDIÁTRICAS TRIAGE, GINECO, MOTIVOS DE NO ACEPTACIÓN, % OCUPACIONAL, REFERENCIA Y CONTRARREFERENCIA y PACIENTES OBSERVADOS (¿es ATENCIONES PEDIATRICAS OBSERVACIONES?). ¿Cómo se llaman en Power BI y desde qué botón se llega? ¿QUIMIOTERAPIA y RADIOTERAPIA se abren desde CANCEROLOGÍA de INDICADORES? ¿ESPECIALIDAD IMAGENES es la «AREA DE SERVICIO IMAGENES» de la documentación? — dónde: `Observaciones › Nombre de página y Propósito (desde qué botón se llega) de esas páginas`.
25. **ATE-25** Páginas sin visuales ni documentación: ATENCIONES PEDIATRICAS OBSERVACIONES, DISTRIBUCION DE ATENCIONES EN UNIDAD NEUROCARDIOVASCULAR, Duplicado de DETALLE ESPECIALIDADES, Página 1, PROMEDIO ESTANCIA y TIPO LABORATORIO. ¿Se usan (y qué muestran) o se eliminan? — dónde: `nombre_funcional, Propósito y Observaciones › Bloque deducido de esas páginas`.
26. **ATE-26** ¿Qué hace el botón PUERTA de INDICADORES (los marcadores de servicio filtran FACT_EGRESOS[EGRESO_PUERTA])? ¿A dónde lleva el último botón de vista de OPORTUNIDAD URGENCIAS y el botón Detalle de LABORATORIO? ¿Qué medida y filtros usa el medidor de consulta general de DETALLE ESPECIALIDADES? — dónde: `indicadores.md › Visuales › Botón PUERTA; oportunidad_urgencias.md › Botones de vista; laboratorio.md › Botón Detalle; detalle_especialidades.md › Medidor general`.
27. **ATE-27** ¿Se pueden retirar las tablas sin uso Hoja1, UNIDAD CARDIONEUROVASCULAR, IMAGENES_CARDIOLOGIA, IMAGENES_ECOGRAFIA, IMAGENES_OTRAS y VistaServicios? — dónde: `_diccionario.md › Observaciones › Tablas sin uso aparente; Tablas › VistaServicios`.
28. **ATE-28** ¿Quién actualiza el libro DATOS EPIDEMIOLOGIA.xlsx (históricos mensuales) y el archivo de gestantes «partos MSPS», y con qué frecuencia? — dónde: `_diccionario.md › Observaciones › Pendientes de negocio; _general.md › Históricos mensuales`.

## BRIEFING HOSPITALARIO

### Afecta una tarjeta o un indicador visible

1. **BRI-1** En DETALLE NEDOCS, ¿las variables C (espera de consulta) y D (espera de cama) de GH_NEDOCS se registran en horas o en minutos? La fórmula usa los coeficientes estándar (5,64 y 0,93), que suponen horas; la tabla solo guarda el corte actual, así que los datos no lo aclaran. — dónde: `detalle_nedocs.md › Indicadores › C espera de consulta / D espera de cama; _diccionario.md › Observaciones › Unidades de NEDOCS`.
2. **BRI-2** La tarjeta CONSULTAS URGENCIAS cuenta solo los triages de ayer clasificados I, II o III (CONSULTAS_REALIZADAS = 0); los IIP, IIS y IIIU quedan fuera. ¿Ese es el criterio correcto de «consulta de urgencias»? — dónde: `_diccionario.md › Observaciones › CONSULTAS_REALIZADAS`.
3. **BRI-3** En %OCUPACION de GESTIÓN CAMAS el numerador (camas ocupadas) incluye las camas de expansión (EXP) y OH, que el denominador excluye. ¿Es intencional (sí/no)? — dónde: `gestion_camas.md › Observaciones › Numerador de ocupación sin exclusiones`.
4. **BRI-4** EGRESOS EFECTIVOS HOY: si el ingreso tiene epicrisis de otro día y orden de salida de hoy, cuenta 0. ¿Debe contar como egreso efectivo (sí/no)? — dónde: `egresos_probables.md › Observaciones › Caso con epicrisis y orden`.
5. **BRI-5** La tarjeta IMAGENES TOMADAS cuenta servicios (filas) y no suma la cantidad (SERCANTID). ¿Debe sumar la cantidad? — dónde: `imagenes_diagnosticas.md › Observaciones › Conteo de imágenes`.
6. **BRI-6** La página OCUPACIÓN POR ESTANCIA no está en el PBIP y su tabla PACIENTES POR ESTANCIA ya no existe en el modelo. ¿Se retiró la página (sí/no)? Si sí, se elimina su documentación. — dónde: `ocupacion_por_estancia.md (Indicadores y Observaciones)`.

### Columnas, visuales y reglas

7. **BRI-7** En DETALLE OCUPACIÓN ColorFila pinta amarillo desde 4 días de estancia, pero la leyenda empieza en 6. ¿El umbral correcto es 4 o 6 días? — dónde: `detalle_ocupacion.md › Observaciones › Semáforo y leyenda no coinciden`.
8. **BRI-8** ¿La tarjeta A2 de NEDOCS («CAMAS EN EL SERVICIO DE URGENCIAS») es el total de camas de urgencias o las disponibles? — dónde: `detalle_nedocs.md › Observaciones › Descripción de A2`.
9. **BRI-9** ¿Qué significan las siglas SAMYL (alistamiento de camas), OH (camas excluidas de la ocupación), CAMA ACV / ruta ACV (12 camas fijas) y PAS y PCG (tipos de convenio)? — dónde: `_diccionario.md › Observaciones › Siglas; _general.md › Sigla OH; gestion_de_camas.md › SAMYL; gestion_camas.md › Marcador CAMAS_ACV; convenios.md › Siglas PAS y PCG`.
10. **BRI-10** ¿Qué regla calcula MOSTRAR_6TO en la vista CAMAS_DISPONIBLES? Vale 0 o 1 y hoy el 0 solo marca parte de las camas de SALA AZUL 3 PISO, que así quedan fuera de la ocupación. — dónde: `gestion_camas.md › Observaciones › Columna MOSTRAR_6TO; _diccionario.md › Observaciones › Vistas de origen`.
11. **BRI-11** Nombres de los estados usados como filtro: solicitud de cama (estados 2, 3, 4, 5 y 8), recepción (OidEstado 7), remisión (EstadoOid 1 y EstadosRecOid 4; el estado del trámite solo muestra «Aprobar» en los datos) y solicitud y historial del briefing (1, 2, 3). ¿Puede indicar el nombre de cada uno o la tabla de Dinámica/PLANILLAUSUARIO que los describe? — dónde: `solicitud_camas.md, seguimiento_recepcion.md, seguimiento_remisiones.md, detalle_briefing.md › Observaciones › Significado de estados`.
12. **BRI-12** ¿Qué servicios son los subgrupos de cama 12 y 16 que INGRESOS excluye, y qué marca ADNINGRESO.AIINGCORCU = 1? — dónde: `ingresos_y_egresos.md › Observaciones › Subgrupos 12 y 16 y AIINGCORCU`.
13. **BRI-13** ¿La vista CD_EGRESOS usa la misma ventana de 7:00 de ayer a 7:00 de hoy que INGRESOS? — dónde: `ingresos_y_egresos.md › Observaciones › Periodo de egresos`.
14. **BRI-14** En PACIENTES EMERGENCIA, ¿«EPS» y «ADRES» en OBSERVACION indican quién paga la atención? — dónde: `pacientes_emergencia.md › Observaciones › Significado de las observaciones`.

### Páginas, navegación y mantenimiento

15. **BRI-15** ¿Remisión es la salida de pacientes del hospital hacia otra entidad y recepción la llegada desde otra entidad (sí/no)? — dónde: `_general.md › Observaciones › Sentido de remisión y recepción`.
16. **BRI-16** ¿Con qué frecuencia se actualiza el conjunto de datos en el servicio y quién mantiene al día los Excel de SharePoint (REPS 2025, CONVENIOS 2026, emergencia)? — dónde: `_general.md › Fuentes de datos › Modo de carga; reps.md › Observaciones › Actualización manual`.
17. **BRI-17** ¿Se pueden retirar ESTADOS CAMA, Tabla7 y ORDEN CAMAS (sin visuales), la copia SEGUIMIENTO REMISION y la página INGRESOS Y EGRESOS POR SERVICIO de la versión de marzo (¿sigue existiendo?)? — dónde: `_diccionario.md › Tablas sin visual; seguimiento_remision.md › Página duplicada; ingresos_y_egresos.md › Versión de marzo; ocupacion_por_estancia.md › Botones copiados`.

## TABLERO TIEMPOS URGENCIAS

### Afecta una tarjeta o un indicador visible

1. **URG-1** Tiempo de estancia y TIEMPO_URGENCIAS[TiempoMinutosSalidaUrgencias] (que está en horas) solo tienen valor si facturación recibió la historia antes de la orden de salida y valen 0 si enfermería la entregó después. ¿Esos casos deben excluirse del promedio en lugar de contar 0? — dónde: `tiempo_estancia.md › Estancia con historia en facturación; _general.md › Columna con nombre engañoso`.
2. **URG-2** En RESUMEN D la tarjeta de triage cuenta con 0 minutos a los pacientes sin turno, y TIEMPOS TRIAGE DIA los excluye. ¿Deben excluirse también en la tarjeta (sí/no)? — dónde: `resumen_d.md › Pacientes sin turno en el promedio de triage`.
3. **URG-3** Límite de espera de egreso: la tabla de EGRESOS DIA usa 360 minutos y el indicador del resumen 720. ¿Cuál es el oficial? — dónde: `egresos_dia.md › Límites distintos`.
4. **URG-4** En RESUMEN las tarjetas de admisión y de consulta filtran tipos de triage distintos y el gráfico ninguno. ¿Qué clasificaciones deben entrar en todos? — dónde: `resumen.md › Criterios de triage distintos`.

### Columnas, visuales y reglas

5. **URG-5** Los triages IIP e IIS se muestran como II pero no entran en las columnas TRIAGE_II de CONSULTAS_DIA y EN_ESPERA_CONSULTA. ¿Deben contarse como triage II (sí/no)? — consulta urgencias-01; dónde: `_diccionario.md › Triage IIP e IIS; consultas_dia.md › IIP e IIS excluidos`.
6. **URG-6** Catálogos de Dinámica sin descripción: ¿a qué nivel (I a V) corresponden los OID de clasificación 2, 7, 9, 16, 17, 18 y 19 de ADMISIONES_DIA; qué son los conceptos de turno 1 a 7 y 17 (HCNCONCOTRI); los tipos de indicación 5 y 6 (¿salida o alta?); los estados 1, 2 y 3 de la solicitud de hospitalización; y los valores 30 a 39 de CCMPACDOC excluidos en consultas prioritarias? — dónde: `admisiones_dia.md › Identificadores de clasificación; tiempos_triage_dia.md › Conceptos de turno; egresos_dia.md › Tipos de indicación 5 y 6; hospitalizacion_dia.md › Estados de la solicitud; consultas_prioritarias.md › Valores de CCMPACDOC`.
7. **URG-7** Listas de espera: ¿deben excluirse los pacientes ya egresados (EGRESOS DIA), los turnos de días anteriores sin cerrar (TIEMPOS TRIAGE DIA) y mostrarse las interconsultas con más de 48 horas sin respuesta (INTERCONSULTAS DIA)? — dónde: `egresos_dia.md › Espera sin excluir egresados; tiempos_triage_dia.md › Turnos sin cerrar; interconsultas_dia.md › Esperas de más de 48 horas ocultas`.
8. **URG-8** ¿EXAMENES debe limitarse al área de laboratorio (15) como LABORATORIOS_DIA, y LABORATORIOS debe mostrar todos los exámenes de cada paciente en vez de uno? — dónde: `examenes.md › Sin filtro de laboratorio; laboratorios.md › Un examen por paciente`.
9. **URG-9** Conteos y fechas de los históricos: ¿INICIO TRATAMIENTO HISTORICOS debe contar ingresos distintos; el mapa de calor de admisiones debe usar la fecha de admisión para el día; y OBSERVACION HISTORICO debe fechar por el fin de la observación a los pacientes sin egreso? — dónde: `inicio_tratamiento_historicos.md › Conteo de ingresos; mapa_de_calor_admisiones.md › Día de la semana; observacion_historico.md › Pacientes sin egreso`.
10. **URG-10** TIEMPO ASIGNACION CAMAS incluye la espera de consulta e ingreso. ¿Debe medir solo la asignación de cama de hospitalización? — dónde: `tiempo_asignacion_camas.md › Qué mide realmente`.
11. **URG-11** CONSULTAS PRIORITARIAS mide la anticipación de la cita, no la espera real (CCMFECCUM no se usa). ¿Debe medir la espera hasta el cumplimiento? ¿Y qué significan los colores del semáforo por número de citas? — dónde: `consultas_prioritarias.md › Espera real no medida; Interpretación del semáforo de citas`.

### Páginas, navegación y mantenimiento

12. **URG-12** ADMISIONES_DIA e INGRESOS_DIA están en Import y no se actualizan en tiempo real como las demás tablas del día. ¿Deben pasar a DirectQuery? ¿Cada cuánto se actualiza el conjunto de datos en el servicio? — dónde: `_general.md › Tablas del día en Import; Actualización programada; admisiones_dia.md; ingresos_dia.md`.
13. **URG-13** Entre las 7:00 p. m. y la medianoche el Calendario (TODAY en UTC) puede ir un día adelante de las tablas del día (GETDATE del servidor). ¿Se corrige la zona horaria (sí/no)? — dónde: `_general.md › Fecha de referencia`.
14. **URG-14** Páginas y restos: ¿se conserva RESUMEN DIA; se agrega un botón a TIEMPO ASIGNACION CAMAS o se elimina; existe el botón Azul (medicina prepagada) en la versión publicada; necesita IMAGENES DIA leyenda y semáforo; se elimina EN ESPERA INGRESO[TIEMPO_ESPERA]; se necesita la relación inactiva OBSERV_HIST[INGRESO] → IMAGENES[INGRESO]? — dónde: `resumen_dia.md; tiempo_asignacion_camas.md › Página inaccesible; _general.md › Botón Azul; imagenes_dia.md; _diccionario_columnas.md › EN ESPERA INGRESO[TIEMPO_ESPERA]; _diccionario.md › Relación inactiva`.

## TABLERO FINANCIERA

### Afecta una tarjeta o un indicador visible

1. **FIN-1** La tarjeta FACTURACIÓN de INICIO suma lo facturado sin restar devoluciones y el gráfico, también titulado FACTURACIÓN, usa la neta ([NETA]). ¿La tarjeta debe mostrar la facturación bruta o la neta? — dónde: `inicio.md › Observaciones › Facturación bruta en la tarjeta`.
2. **FIN-2** Ingresos abiertos: la tarjeta de COMPARATIVO usa TOTAL_ING_ABIERTOS (valor entidad + valor paciente) y la de INICIO usa VLSERVICIO; los datos muestran que no coinciden (TOTAL_ING_ABIERTOS queda por debajo). ¿Cuál es el valor oficial de ingresos abiertos? — consulta financiera-06; dónde: `comparativo.md › Observaciones › Ingresos abiertos con dos columnas`.
3. **FIN-3** ¿Con qué regla calcula la consulta de origen el costo estimado ANALISIS_RENTABILIDAD[COSTOVARIACION] (columna «Estimado» de COSTO ESTIMADO)? — dónde: `costo_estimado.md › Indicadores › Costo estimado; _diccionario.md › ANALISIS_RENTABILIDAD[COSTOVARIACION]`.

### Columnas, visuales y reglas

4. **FIN-4** ¿El %PARTICIPACIÓN del gráfico de aseguradores de INICIO debe calcularse sobre los 10 aseguradores visibles o sobre el total? — dónde: `inicio.md › Observaciones › Participación entre los 10 primeros`.
5. **FIN-5** ¿Qué es un «ingreso abierto» (qué estados de ingreso cuentan) y qué significa «ACTUAL» en INGRESOS ABIERTOS ACTUAL: corte a hoy o solo el mes en curso? — dónde: `_general.md › Definiciones › Ingresos abiertos; ingresos_abiertos_actual.md`.
6. **FIN-6** El segmentador MOSTRAR MEDICAMENTOS de CUPS («SOLO CUPS» / «MEDICAMENTOS Y SUMINISTROS»): ¿con cuál opción debe arrancar? — consulta financiera-01; dónde: `cups.md › Observaciones › Valores de mostrar medicamentos`.

### Páginas, navegación y mantenimiento

7. **FIN-7** ¿Se retira la medida [Prueba CostoUnitario] (columna con nombre técnico) de Duplicado de Duplicado de COSTOS X MESES? — dónde: `_diccionario.md › Observaciones › Medida de prueba`.
8. **FIN-8** COMPARATIVO, FACTURACIÓN GENERAL, Duplicado de FACTURACIÓN GENERAL, COSTOS X MESES, Duplicado de Duplicado de COSTOS X MESES y COSTOS ANTERIOR no se alcanzan desde INICIO. ¿Se eliminan (sí/no, por página)? — dónde: `_general.md › Observaciones › Páginas sin acceso`.
9. **FIN-9** ¿Se renombra «Duplicado de Duplicado de FACTURACIÓN GENERAL» (la página en uso) a FACTURACIÓN GENERAL? — dónde: `duplicado_de_duplicado_de_facturacion_general.md › Observaciones › Nombre de copia`.
10. **FIN-10** COSTO ESTIMADO filtra años fijos y no muestra 2026, aunque ANALISIS_RENTABILIDAD ya trae meses de 2026. ¿Se agrega 2026? — consulta financiera-07; dónde: `costo_estimado.md › Observaciones › Gráficos sin 2026`.
11. **FIN-11** En COSTOS ANTERIOR el %RENT de las filas se suma; ¿debe promediarse? — dónde: `costos_anterior.md › Observaciones › Porcentaje sumado`.
12. **FIN-12** ¿Las líneas de promedio de ANALISIS DE RENTABILIDAD y COSTO ESTIMADO (sobre VLRSERVICIOENORDEN, TOTAL_COSTO y RENTABILIDAD_TOTAL) se muestran a propósito? — dónde: `analisis_de_rentabilidad.md / costo_estimado.md › Observaciones › Promedios sobre otras columnas`.

## DEMANDA INSATISFECHA

### Afecta una tarjeta o un indicador visible

1. **DEM-1** Camas: casi todas las solicitudes tienen EstadoOid 4 y solo esas marcan DEMANDA_INS (tarjeta HOSPITALIZACIÓN y NO ASIGNADAS), mientras TOTAL_SOLICITUD_CAMAS cuenta las de estado distinto de 4 (2, 3, 5 y 12), que son muy pocas. ¿Qué significa el estado 4 y cuál de las dos reglas es la correcta? — dónde: `_diccionario.md › SOLICITUD DE CAMAS[DEMANDA_INS]; Reglas de cama distintas; solicitud_camas.md › Dos reglas de cama; consolidado.md › Reglas de cama distintas`.
2. **DEM-2** Triages: la página TRIAGES filtra TRIAGE[HCCESTADO] = 2 (los datos traen 1, 2 y 3) y CONSOLIDADO no. ¿Qué significan los estados 1, 2 y 3 y debe aplicarse el filtro también en CONSOLIDADO (sí/no)? ¿Qué son los conceptos HCNCONCOTRI 1 a 7? — dónde: `_diccionario.md › TRIAGE[HCCESTADO]; Triages: filtro solo en su página; triages.md › Clasificaciones incluidas / Filtro de página; consolidado.md › Triages sin filtro de estado`.
3. **DEM-3** Cirugías: el denominador de oportunas (CIRUGIAS REALIZADAS) incluye todas las solicitudes planeadas, no solo las operadas, y una solicitud cancelada tras más de 45 días cuenta como demanda insatisfecha. ¿Ambas reglas son correctas (sí/no cada una)? — dónde: `_diccionario.md › Cirugías realizadas; consolidado.md › Cirugías realizadas; cirugias.md › Cirugías canceladas`.

### Columnas, visuales y reglas

4. **DEM-4** Citas: todas las citas con causa de cancelación tienen CCMESTADO = 1 y el nombre del estado vacío. ¿Qué significa ese estado 1? — dónde: `citas.md › Observaciones › Estado de la cita; Reglas de negocio › Causas incluidas`.
5. **DEM-5** SOLICITUD DE CAMAS une HPNSUBGRU por d.OID = a.serviciooid (OID del subgrupo igual al servicio solicitante). ¿Es correcta esa unión o el nombre de subgrupo puede salir equivocado? — dónde: `solicitud_camas.md › Observaciones › Unión de subgrupo`.

### Páginas, navegación y mantenimiento

6. **DEM-6** Los promedios mensuales incluyen el mes en curso incompleto. ¿Debe excluirse (sí/no)? — dónde: `_general.md › Observaciones › Promedios con el mes actual`.
7. **DEM-7** La documentación salta la página 6 y la tabla CONTRAREFERENCIA y la medida PROM_TRAMITES_CONTRA no tienen página. ¿Existía una página de contrarreferencia? ¿Se agrega o se retiran esa tabla y medida? — dónde: `_general.md › Observaciones › Página 6 ausente`.

## TABLERO PERFIL DE MORBILIDAD

### Afecta una tarjeta o un indicador visible

1. **MOR-1** MATRIZ 2024 tiene ingresos repetidos en todos los años. ¿Las tarjetas Egresos (INICIO) y Atenciones (FACTURACION, PERFIL DE MORBILIDAD) deben contar ingresos distintos (MATRIZ 2024[Ingreso]) en lugar de filas? — dónde: `inicio.md › Indicadores › Egresos; facturacion.md y perfil_de_morbilidad.md › Indicadores › Atenciones`.
2. **MOR-2** FACTURACION tiene varias facturas por ingreso. ¿El «Promedio de facturación» debe ser por factura (AVERAGE de VALOR_FACTURA) o por atención (total facturado / egresos)? — dónde: `facturacion.md › Indicadores › Promedio de facturación`.
3. **MOR-3** Desde 2026 prácticamente ningún egreso encuentra su factura (los egresos traen el identificador interno del ingreso y FACTURACION el consecutivo). ¿Se corrige la llave del cruce (sí/no)? — dónde: `facturacion.md › Observaciones › Cruce incompleto en 2025`.

### Columnas, visuales y reglas

4. **MOR-4** El botón ONCOLOGICO de INICIO ¿filtra con ONCOLOGICO[ONCOLOGICO], MATRIZ 2024[ONCOLOGICOM] o MATRIZ 2024[P_ONCOLOGICO]? — dónde: `inicio.md › Observaciones › Columna del botón oncológico; _diccionario.md › Observaciones › Marca oncológica dispersa`.
5. **MOR-5** Los botones de servicio de INICIO ¿usan MATRIZ 2024[SERVICIOS] o Servicio_Agrupado? ¿Las barras usan GRD_R, CMD_R y CIE10_R? — dónde: `inicio.md › Reglas de negocio › Botones de servicio; Ejes de diagnóstico`.

### Páginas, navegación y mantenimiento

6. **MOR-6** FACTURACION PERIOPERATORIA: la consulta de PERIOPERATORIA tiene comentada la columna VALOR_FACTURA. ¿De dónde sale la facturación de esa página? — dónde: `facturacion_perioperatoria.md › Propósito`.

## TABLERO REFERENCIA

### Afecta una tarjeta o un indicador visible

1. **REF-1** Las tarjetas de INICIO, DETALLE RECEPCIONES, DETALLE ACEPTADOS y DETALLE NO ACEPTADOS: «Cantidad de solicitudes» ¿cuenta REFERENCIA[OID] (distinto)? «Tiempo promedio de respuesta» ¿es el promedio (no la mediana) de TIEMPO_REMISION en horas? «Promedio de edad» ¿es el promedio de ANOS? — dónde: `inicio.md, detalle_recepciones.md, detalle_aceptados_recepcion.md, detalle_no_aceptados_recepcion.md › Indicadores`.
2. **REF-2** DETALLE REMISION: «Remisiones» ¿cuenta OidRemision distintos de CONTRARREFERENCIA? «Tiempo promedio de respuesta» ¿promedia TIEMPO_RESPUESTA en horas? — dónde: `detalle_remision.md › Indicadores`.
3. **REF-3** REFERENCIA debería traer las llamadas de los últimos 30 días, pero el 2026-11-03 sus datos terminaban en mayo de 2026. ¿Está detenida la actualización programada del conjunto de datos? — dónde: `_general.md › Observaciones › Datos sin actualizar`.

### Columnas, visuales y reglas

4. **REF-4** ¿Qué contiene CONTRARREFERENCIA[Expr3] (columna sin nombre de la vista SEGUIMIENTO_REMISIONES_DW) y CONTRARREFERENCIA[Nombre] es el estado de la remisión? — consulta referencia-01; dónde: `_diccionario.md › Columnas clave › CONTRARREFERENCIA[Expr3], [Nombre]`.
5. **REF-5** La mayoría de las solicitudes no tiene fecha de aceptación ni de no aceptación y su tiempo de respuesta crece hasta hoy. ¿Deben excluirse del tiempo promedio de respuesta (sí/no)? — dónde: `_general.md › Observaciones › Solicitudes sin respuesta; inicio.md › Especialidad vacía`.

## TABLERO CONTROL FACTURACION

### Afecta una tarjeta o un indicador visible

1. **CFA-1** PROCESO FACTURACION: «Egresos gestionados» ¿es el conteo distinto de ingresos? «Total facturado» ¿suma MONTO_FACTURADO de FACTURACION PERFILES? «Gestiones» ¿cuenta filas o suma? (la página no está en el PBIP local) — dónde: `proceso_facturacion.md › Indicadores`.
2. **CFA-2** El gráfico «Tiempo entre el egreso del paciente y la prefactura» mide de la entrega de ESTACION DE ENFERMERIA a la entrega de FACTURADOR SERVICIO. ¿Se cambia el título o el cálculo para que parta del egreso? — dónde: `_diccionario.md › Observaciones › TIEMPO_PREFACTURA; tiempos.md › Observaciones › Egreso o entrega; _general.md › Tiempo de egreso a prefactura`.

### Columnas, visuales y reglas

3. **CFA-3** ¿Qué marca ADNEGRESO.AEEGRCORCU = 1 (egresos que FACTURACION PENDIENTE excluye)? — dónde: `facturacion_pendiente.md › Reglas de negocio › Exclusión de egresos`.
4. **CFA-4** Los tiempos de FACTURACION PERFILES se calculan con fechas sin hora (siempre múltiplos de 24 h). ¿Se quiere precisión por hora? — dónde: `_diccionario.md › Observaciones › Horas múltiplos de 24`.
5. **CFA-5** FACTURACION PENDIENTE une TFACTURACI por el OID del ingreso y las demás consultas por el consecutivo (AINCONSEC). ¿Cuál es la llave correcta? — dónde: `facturacion_pendiente.md › Observaciones › Llave de trazabilidad`.
6. **CFA-6** FACTURACION PENDIENTE filtra HOSPITALARIO a nivel de página, aunque la tabla también trae pendientes AMBULATORIO: ¿se quita el filtro o se quita el botón AMBULATORIO? — dónde: `facturacion_pendiente.md › Observaciones › Botón AMBULATORIO`.
7. **CFA-7** Los segmentadores AREA SERVICIO de FACTURADORES y RESUMEN FACTURACION no filtran (son de ULT_GESTION). ¿Se cambian a la columna de la tabla de la página? — dónde: `facturadores.md › Observaciones › Segmentador de área`.
8. **CFA-8** En EN PROCESO AUDITORIA MEDICAMENTOS los filtros se contradicen; ¿cuál es el filtro correcto? Y en las páginas EN PROCESO, la tabla «DIFERENCIA DE DIAS DESDE FECHA SALIDA PACIENTE» mide desde FECHA_RECIBE: ¿se corrige el título o el cálculo? — dónde: `en_proceso_*.md › Observaciones › Filtros contradictorios; Título de la tabla de diferencia`.

### Páginas, navegación y mantenimiento

9. **CFA-9** En las consultas de tiempos la auditoría se liga a los perfiles 4 o 5 por el usuario que entrega; ¿un mismo usuario puede trabajar en ambos perfiles (duplicaría filas)? ¿Y un ingreso con varias facturas debe contarse una vez en PROCESO FACTURACION? — dónde: `_general.md › Observaciones › Auditor por usuario; proceso_facturacion.md › Observaciones › Unión de facturas; inicio.md › Observaciones › Unión de auditorías`.
10. **CFA-10** ¿Cuál es el nombre en Power BI de las páginas AUDITORES EXTERNOS y PROCESO FACTURACION y qué filtro de página tiene AUDITORES EXTERNOS? FACTURACION PERFILES no tiene ningún registro con ese perfil: ¿la página se retira o el perfil cambió de nombre? — dónde: `auditores_externos.md › Propósito y Reglas de negocio; proceso_facturacion.md › Propósito`.
11. **CFA-11** «Duplicado de INICIO» (versión de trabajo de PROCESO FACTURACION, con la columna rota SFANETOFAC) y TRAZABILIDAD FACTURACION (sin botón de entrada) ¿siguen en uso o se eliminan? — dónde: `duplicado_de_inicio.md; proceso_facturacion.md › Sin página en el PBIP; trazabilidad_facturacion.md › Sin botón de entrada`.

## ASIGNACION DE CITAS

### Afecta una tarjeta o un indicador visible

1. **CIT-1** La tarjeta CONSULTAS ASIGNADAS de INICIO no filtra el estado y cuenta también las citas anuladas. ¿Debe excluir las anuladas? — dónde: `inicio.md › Observaciones › Consultas asignadas incluye anuladas`.
2. **CIT-2** Las tarjetas TOTAL GESTIONES de MAPA DE CALOR ASESORES y MAPA DE CALOR X DIA tienen un filtro CITAS_ASIGNADAS[CCMESTADO] = 1 que solo actúa por la relación con ASEGURADORA. ¿Ese filtro es intencional (sí/no)? — dónde: `mapa_de_calor_asesores.md / mapa_de_calor_x_dia.md › Observaciones › Filtro ajeno en la tarjeta`.

### Columnas, visuales y reglas

3. **CIT-3** En EN_ESPERA, para una solicitud ya asignada, ¿FECHA es la fecha de creación de la solicitud o la del cambio a asignada? (afecta los días para asignación) — dónde: `_general.md › Observaciones › Fecha de las solicitudes asignadas`.
4. **CIT-4** El estado 3 de la cita aparece como CANCELADO e Inasistida. ¿Cuál es su nombre correcto: inasistida o cancelada? — dónde: `_diccionario.md › Observaciones › Nombres de estado engañosos`.
5. **CIT-5** ¿Los 21 pacientes excluidos por identificador en CITAS_ASIGNADAS y AGENDA_ESPECIALISTAS son pacientes de prueba? ¿Quién mantiene la lista fija de unos 100 médicos de AGENDA_ESPECIALISTAS? — dónde: `_general.md › Reglas de negocio › Pacientes excluidos; _diccionario.md › Observaciones › Listas fijas en la consulta`.
6. **CIT-6** Las solicitudes de preagendamiento no traen aseguradora ni clasificación MAESTROS, así que esos filtros las excluyen. ¿Es intencional? — dónde: `_diccionario.md › Observaciones › Preagendamientos sin aseguradora`.
7. **CIT-7** INASISTIDAS por DIA agrupa por el día en que se asignó la cita (Calendario se une por fecha de asignación), no por el día de la cita. ¿Es lo deseado? — dónde: `oferta_especialidades.md › Observaciones › Día de las inasistencias`.
8. **CIT-8** DISPO X ESPECIALIDAD parte de las citas, así que un bloque de agenda sin ninguna cita no aparece. ¿Debe mostrarse la agenda vacía? — dónde: `dispo_x_especialidad.md › Observaciones › Agenda sin citas`.
9. **CIT-9** La tabla de ASIGNADAS X ASESOR muestra una fila con asesor vacío (gestiones de usuarios sin rol CITAS). ¿Se deja o se filtra? — dónde: `asignadas_x_asesor.md › Observaciones › Fila sin asesor`.

### Páginas, navegación y mantenimiento

10. **CIT-10** DETALLE CITAS ASIGNADAS DÍA (usa ASIGNADAS_ACTIVIDAD y AGENDA_ESPECIALISTAS[Nombre_Medico], que no existen) y DISPONIBILIDAD X ESPECIALIDAD (usa AGENDA DISPONIBLE(MINUTOS), que no existe; casi copia de DISPO X ESPECIALIDAD) están rotas. ¿Están en desuso y se pueden retirar? — dónde: `detalle_citas_asignadas_dia.md, disponibilidad_x_especialidad.md; _diccionario.md › Observaciones › Página rota, Páginas casi duplicadas`.
11. **CIT-11** EN ESPERA X ESPECIALIDAD tiene dos segmentadores de mes y ninguno de día. ¿Uno de ellos debía ser de día? — dónde: `en_espera_x_especialidad.md › Observaciones › Segmentador de mes repetido`.

## TABLERO NAOS

### Afecta una tarjeta o un indicador visible

1. **NAO-1** ¿Qué criterios usa la vista TABLERO_NAOS para que un paciente aparezca en LISTADO (tarjeta PACIENTES) y cuándo marca un paciente como PACIENTE PRIORIZADO en lugar de su convenio (medicina prepagada, plan complementario o póliza)? — dónde: `_general.md › Observaciones › Vista sin documentar; listado.md › Observaciones › Clasificación sin documentar; _diccionario.md › Observaciones › Vista TABLERO_NAOS`.
2. **NAO-2** CIRUGÍAS PENDIENTES no filtra por fecha ni egreso. ¿Debe incluir pacientes ya egresados o ambulatorios? — dónde: `cirugias_pendientes.md › Observaciones › Sin filtro de fecha ni de egreso`.

### Columnas, visuales y reglas

3. **NAO-3** ¿Qué estado de la solicitud de cirugía es el 4 y qué tipo de cirugía es TipoCirugiaOid = 1 (¿programada?)? — dónde: `cirugias_pendientes.md › Observaciones › Estado 4 sin nombre, Tipo de cirugía 1`.
4. **NAO-4** GESTION CLINICA excluye solicitudes en estados 4, 5, 6 y 12, incluye la categoría 404 y no filtra HCAESTADO (la documentación solo menciona el estado 4). ¿Qué significan esos estados y el estado 3 del historial, y cuál es la regla vigente? — dónde: `gestion_clinica.md › Observaciones › Significado de estados; _diccionario.md › Observaciones › Consulta de gestión clínica distinta de la documentación`.
5. **NAO-5** En EXAMENES (ESTADO_EXAMEN vale PENDIENTE o RESULTADO DISPONIBLE), ¿la tabla debe ocultar los ingresos sin exámenes pendientes? — dónde: `examenes.md › Observaciones › Filas sin pendientes, Consulta de EXAMENES_NAOS`.

### Páginas, navegación y mantenimiento

6. **NAO-6** ¿Qué significa la sigla NAOS? — dónde: `_general.md › Observaciones › Significado de NAOS`.

## TABLERO CVC

### Afecta una tarjeta o un indicador visible

1. **CVC-1** ¿Las tarjetas TOTAL COMPRAS CON AUMENTO y CON DISMINUCIÓN son la suma de COMPRA_TOTAL (cantidad × último costo) de los registros con ESTADO AUMENTÓ y DISMINUYÓ? (TOTAL PRODUCTOS ya se explica: cuenta productos distintos) — consulta cvc-01; dónde: `cvc.md › Indicadores › Total compras con aumento / con disminución`.
2. **CVC-2** El gráfico TENDENCIA DE COSTOS se rotula «Desviación estándar» (%). ¿Es la desviación estándar de variacion_porcent por mes u otra columna? (el modelo no tiene esa medida y el PBIP no trae los visuales) — dónde: `cvc.md › Indicadores › Desviación de la tendencia de costos`.

### Columnas, visuales y reglas

3. **CVC-3** La primera compra de cada producto queda con ESTADO AUMENTÓ porque no tiene costo anterior (pasa con todos los productos), y si el costo anterior es ≤ 1 la variación se mide contra el costo promedio. ¿La primera compra debe quedar sin estado (o como «primera compra»)? — dónde: `cvc.md › Observaciones › Primera compra como aumento; _diccionario.md › Observaciones › Base del costo anterior`.
4. **CVC-4** En COSTOS_VARIACION el costo anterior es el mayor costo distinto del último, no el inmediatamente previo. ¿Es la intención? — dónde: `_diccionario.md › Observaciones › Costo anterior en COSTOS_VARIACION`.

### Páginas, navegación y mantenimiento

5. **CVC-5** ¿Quién actualiza el Excel «Regulados y No Regulados Dinamica Gerencial» y cada cuánto? — dónde: `_diccionario.md › Observaciones › Fuente de regulados`.
6. **CVC-6** ¿Qué significa la sigla CVC y qué almacén es el código 062? — dónde: `_general.md › Observaciones › Sigla CVC, Almacén 062; _diccionario.md › Observaciones › Sigla y almacén`.

## TABLERO RECEPCION TECNICA

### Afecta una tarjeta o un indicador visible

1. **REC-1** La tarjeta TIEMPO PROMEDIO EN GESTION de PROMEDIO GESTION MENSUAL suma los promedios de todos los meses y estados (≈ 86) en lugar de promediarlos (las líneas están entre 0 y 7 días). ¿Debe mostrar el promedio? — dónde: `promedio_gestion_mensual.md › Observaciones › Escalas distintas; _diccionario.md › Observaciones › Suma de promedios`.
2. **REC-2** La tarjeta PEDIDO GESTIONADOS suma CANTIDAD_REGISTROS, que cuenta estados terminados y no pedidos distintos. ¿Debe contar pedidos distintos? — dónde: `_diccionario.md › Observaciones › Pedidos gestionados`.

### Columnas, visuales y reglas

3. **REC-3** TIEMPO_1 a TIEMPO_5 pueden salir negativos si las etapas se registran fuera de orden. ¿Las tarjetas y la tabla deben excluir esos registros? — dónde: `detalle_recepcion_tecnica.md / _diccionario.md › Observaciones › Tiempos entre etapas`.
4. **REC-4** PROMEDIO GESTION trae 6 meses y PROMEDIO GESTION MENSUAL desde el 1 de enero de 2025. ¿Cuál ventana es la vigente? — dónde: `_diccionario.md › Observaciones › Ventanas distintas`.
5. **REC-5** La consulta de CANTIDADES no filtra cantidad pendiente > 0 ni estado de la solicitud. ¿Cómo se limita a los pendientes (o debe agregarse ese filtro)? — dónde: `cantidades.md › Observaciones › Pendiente sin filtro explícito`.

## TABLERO EPS

### Afecta una tarjeta o un indicador visible

1. **EPS-1** La tarjeta Ocupación de urgencias incluye el servicio SEXTO PISO y excluye las camas con «EXP» en el código (las hay en urgencias, sexto piso, obstetricia, neonatos y segundo piso sur). ¿SEXTO PISO cuenta como urgencias? ¿EXP significa cama de expansión y deben excluirse? — dónde: `_diccionario.md › %OCUPACIONAL[codcama]; Observaciones › Ocupación de urgencias incluye SEXTO PISO; triages_atendidos.md › Ocupación de urgencias`.
2. **EPS-2** [%ATENDIDOS] divide atendidos por llegadas + pendientes acumulados, y los pendientes ya incluyen los de la hora. ¿Es el denominador deseado? — dónde: `_diccionario.md › Observaciones › Denominador de [%ATENDIDOS]; atenciones_admisiones.md`.

### Columnas, visuales y reglas

3. **EPS-3** El porcentaje de atenciones frente a admisiones cruza solo por documento y supera el 100 % (107,48 % en la captura). ¿Se acepta o se cambia el cruce? — dónde: `_diccionario.md › Observaciones › Porcentaje de atenciones frente a admisiones; atenciones_admisiones.md › Cruce solo por documento`.
4. **EPS-4** CONSULTAS PRIORITARIAS no corresponde a triages 4 y 5: ¿cuál es el rótulo correcto? ¿Por qué se excluyen los documentos 30 a 39 y las uniones que pueden dejar citas por fuera son intencionales? — dónde: `_diccionario.md › Consultas prioritarias no son triages 4 y 5; consultas_prioritarias.md`.

### Páginas, navegación y mantenimiento

5. **EPS-5** ATENCIONES_GINECO (ingresos por maternidad) no la usa ninguna página: ¿se retira? — dónde: `_diccionario.md › Observaciones › ATENCIONES_GINECO sin uso visible`.

## TABLERO FARMACIA

### Afecta una tarjeta o un indicador visible

1. **FAR-1** La tarjeta MEDICAMENTOS VENCIDOS de INICIO sale en blanco cuando no hay ajustes por vencimiento en los últimos tres meses. En la captura la página MEDICAMENTOS VENCIDOS mostraba 88: ¿de qué tabla o tarjeta sale ese 88 y cuál debe ver el usuario? — dónde: `inicio.md › Observaciones › Vencidos en blanco`.

### Columnas, visuales y reglas

2. **FAR-2** ¿El filtro ESTADO de SUMINISTROS PENDIENTES usa PENDIENTES_FARMACIA[PENDIENTE] (PENDIENTE/DISPENSADO) y la columna CONSECUTIVO es AINCONSEC (consecutivo del ingreso)? El PBIP no trae los visuales de esa página. — dónde: `_diccionario.md › PENDIENTES_FARMACIA[PENDIENTE]; suministros_pendientes.md › Observaciones › Campos por confirmar`.
3. **FAR-3** Todos los meses dejan una parte de órdenes sin documento de suministro que siguen sumando horas hasta hoy, y por eso los meses antiguos muestran promedios muy altos. ¿Deben excluirse del promedio las órdenes sin documento de suministro? — dónde: `oportunidad_dispensacion.md › Observaciones › Tendencia llamativa`.
4. **FAR-4** «MEDICAMENTOS EN VENCIMIENTO 0-30 DÍAS» filtra mes ≤ 1, y la vista calcula mes en meses calendario (0 incluye los ya vencidos), así que la tarjeta abarca hasta el fin del mes siguiente (cerca de 60 días). ¿Se cambia el rótulo o el filtro (sí/no)? — dónde: `medicamentos_vencidos.md › Observaciones › Días frente a meses`.

### Páginas, navegación y mantenimiento

5. **FAR-5** El botón INVENTARIO lleva a «Duplicado de STOCK MINIMO» (sin visuales en el PBIP). ¿Es esa la página vigente de stock mínimo y qué columnas tiene su tabla? — dónde: `duplicado_de_stock_minimo.md › Observaciones › Página sin visuales; stock_minimo.md › Observaciones › Columnas por confirmar`.
6. **FAR-6** ¿Para qué está Consulta1 (SELECT * FROM DIM_UNIDAD) si ninguna relación, medida ni visual la usa? ¿Se puede retirar? — dónde: `_diccionario.md › Tablas › Consulta1; _general.md › Fuentes de datos › Consulta1`.

## TABLERO ANTIBIOTICOS

### Afecta una tarjeta o un indicador visible

1. **ANT-1** La tarjeta «TOTAL DOSIS SUMINISTRADAS» suma HCCANTIDAD, que está en unidades de presentación (viales, ampollas, tabletas; admite fracciones). ¿Debe sumar unidades, contar aplicaciones (una por administración) o sumar la dosis en mg (HCCANTDOSIS)? — dónde: `_diccionario.md › Observaciones › Pendiente para el dueño`.

### Columnas, visuales y reglas

2. **ANT-2** La consulta excluye HCAESTADO = 6 y toma solo HCRESPUES = 0. ¿Qué significan ese estado 6 y la respuesta 0 (¿orden anulada?, ¿aplicación sin respuesta/no rechazada?)? — dónde: `_general.md › Observaciones › Significado de códigos`.
3. **ANT-3** El estado ACTIVO se calcula como «unidades despachadas menos aplicadas > 0», no con la orden médica vigente. ¿Es el criterio correcto de paciente con tratamiento activo (tarjeta de pacientes activos)? — dónde: `_general.md › Observaciones › Estado ACTIVO por despacho`.

## TABLERO LAVANDERIA

### Afecta una tarjeta o un indicador visible

1. **LAV-1** ¿El peso de LAVANDERIA[Peso] está en kilogramos o en libras? Un pesaje típico por servicio está entre 7 y 27 y en quirófanos ronda 77 (máximo cerca de 250); el rango no basta para decidirlo. — dónde: `pagina_1.md › Indicadores › Peso; _general.md › Definiciones › Peso`.

### Páginas, navegación y mantenimiento

2. **LAV-2** ¿Los segmentadores Año y Mes filtran por Fecha (encabezado) o por FechaRegistro (pesaje)? Casi no cambia el resultado: menos del 1 % de los pesajes cae en otro mes. — dónde: `_diccionario.md › Columnas clave › LAVANDERIA[Fecha]; pagina_1.md › Observaciones › Fecha de los filtros`.
