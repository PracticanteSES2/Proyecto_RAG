# Preguntas pendientes para el propietario de los tableros

Lista de lo que la documentación (`docs_tableros/<grupo>/md/`) todavía marca «Por confirmar» y que no se pudo resolver con el modelo publicado (`data/model_metadata`), el PBIP (`tableros/`), la documentación .docx ni los catálogos. Las preguntas son cerradas: basta con responder sí/no, elegir una opción o dar el dato.

Cómo leerla:

- Va primero lo que cambia una cifra que ve el usuario (tarjetas e indicadores); después columnas, visuales y reglas; al final páginas y mantenimiento.
- «Consulta X» indica una consulta DAX de solo lectura de `tools/consultas_por_confirmar.json` que conviene ejecutar antes: su resultado puede bastar para responder o hacer la pregunta más concreta.
- «Dónde» señala la entrada del .md que se actualiza con la respuesta.
- Para ver el detalle de cada mención: `python -X utf8 tools/por_confirmar.py [--grupo <grupo>]`.

## Estado

- Menciones «Por confirmar» en los .md: 644 → 510 (en los diccionarios: 156 → 112). Corte: 2026-11-03.
- Preguntas para el propietario: 150, de ellas 45 con impacto en tarjetas o indicadores.
- Consultas DAX de solo lectura pendientes de ejecutar: 53 (`tools/consultas_por_confirmar.json`).

| Tablero | Menciones que quedan | Preguntas | Consultas DAX |
|---|---|---|---|
| TABLERO DE ATENCIONES INSTITUCIONALES | 169 | 28 | 11 |
| TABLERO FINANCIERA | 51 | 12 | 7 |
| TABLERO PERFIL DE MORBILIDAD | 51 | 6 | 3 |
| BRIEFING HOSPITALARIO | 38 | 17 | 6 |
| TABLERO TIEMPOS URGENCIAS | 34 | 14 | 1 |
| TABLERO CONTROL FACTURACION | 30 | 12 | 3 |
| TABLERO REFERENCIA | 28 | 4 | 2 |
| DEMANDA INSATISFECHA | 17 | 7 | 3 |
| ASIGNACION DE CITAS | 16 | 11 | 0 |
| TABLERO CVC | 15 | 8 | 3 |
| TABLERO FARMACIA | 15 | 6 | 6 |
| TABLERO EPS | 12 | 6 | 2 |
| TABLERO NAOS | 12 | 6 | 2 |
| TABLERO LAVANDERIA | 9 | 2 | 2 |
| TABLERO RECEPCION TECNICA | 7 | 5 | 0 |
| TABLERO ANTIBIOTICOS | 6 | 5 | 2 |

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
2. **ATE-2** Promedio de estancia de INDICADORES: la medida PROMEDIO_ESTANCIA que cita la documentación ya no existe. ¿El gráfico usa [PROMEDIO_ESTANCIA_TOTAL] o [PROMEDIO_ESTANCIA_TOTAL1] (que se apoya en [ESTANCIA_TOTAL])? ¿Está en días por egreso? (la captura muestra 118 a 148) — consulta atenciones-08; dónde: `indicadores.md › Indicadores › Promedio de estancia; Observaciones › Unidad del promedio de estancia; _diccionario.md › [ESTANCIA_TOTAL]`.
3. **ATE-3** La tarjeta CAPACIDAD INSTALADA muestra 308 camas y las listas fijas de [NUM_CAM_EGRESOS] y [NUMERO_CAMAS] suman 280. ¿De dónde sale el 308 y quién actualiza esas listas de camas por servicio? — consulta atenciones-07; dónde: `indicadores.md › Indicadores › Capacidad instalada; Observaciones › Capacidad instalada sin cuadrar; _diccionario.md › Observaciones › Listas fijas de camas`.
4. **ATE-4** Giro cama: ¿debe contar solo egresos PUERTA o TRASLADO (como dice la documentación y hacen [GIRO_CAMA_ANO_ACTUAL]/[GIRO_CAMA_ANO_ANTERIOR]) o todos los ingresos con egreso del año (como hace hoy [GIRO_CAMA1], el del gráfico)? — dónde: `indicadores.md › Reglas de negocio › Egresos para giro cama; _diccionario.md › Observaciones › Giro cama y tipo de egreso`.
5. **ATE-5** ¿Las constantes de CONSULTAS_AMBULATORIAS son las metas de oportunidad en días: CONSULTA_PRA = 15 (primera vez), CONTROL = 20 (control) y GENERAL = 20 (general)? — dónde: `_diccionario.md › Columnas calculadas › CONSULTAS_AMBULATORIAS[CONSULTA_PRA], [CONTROL], [GENERAL]`.
6. **ATE-6** Las medidas [PRIORITARIAS_*] y [TIEMPO_OPORTUNIDAD_PRIORITARIAS_*] usan columnas que ya no existen (OID_TRIAGE, TIEMPO_PARA_CONSULTA) y CONSULTAS OBSTETRICAS filtra por TIPO_TRIAGE, que tampoco existe. ¿Se corrigen o se retiran? ¿La oportunidad de consulta (OPORTUNIDAD URGENCIAS y OPORTUNIDAD CONSULTA OBSTÉTRICA) se mide con tiempo_consulta o con TIEMPO_CONSULTA_CALCULADA? — dónde: `_diccionario.md › Observaciones › Medidas con columnas que no existen; oportunidad_urgencias.md › Indicadores › Promedio del gráfico; oportunidad_consulta_obstetrica.md › Indicadores y Reglas › Tiempo para consulta; Observaciones › Tarjeta vacía`.
7. **ATE-7** Cirugías: ¿qué valores de ESTADO ACTUAL cuentan como «pendiente» y cuál como «cancelada»? ¿CANCELACIONES usa CIRUGIAS_PENDIENTES u OPORTUNIDAD CIRUGIA y filtra por ESTADO ACTUAL o por la fecha de «Paciente Cancelado»? — consulta atenciones-09; dónde: `pendientes.md › Indicadores › Cirugías pendientes; Observaciones › Definición de pendiente; cancelaciones.md`.

### Columnas, visuales y reglas

8. **ATE-8** ¿Qué significa el estado de ingreso AINESTADO 4 (se excluye junto con el 2, ANULADO) y la marca AIINGCORCU = 1? — dónde: `_general.md › Reglas de negocio › Ingresos excluidos; oportunidad_urgencias.md › Reglas de negocio › Ingresos excluidos; _diccionario.md › Observaciones › Pendientes de negocio`.
9. **ATE-9** ¿Qué significan los estados 1, 2 y 3 de los resultados de patología (los únicos que entran en LABORATORIO PATOLOGICO)? — dónde: `laboratorio_patologico.md › Reglas de negocio › Estados válidos`.
10. **ATE-10** ¿Cuáles son las especialidades con identificador 1, 2, 3, 4, 6, 8, 51, 65, 88, 90 y 129 que CONSULTAS PRIORITARIAS excluye? — dónde: `consultas_prioritarias.md › Reglas de negocio › Especialidades excluidas`.
11. **ATE-11** % OCUPACIONAL: ¿qué significan los estados de cama 1, 2 y 5? ¿La regla «CRIT en el nombre ⇒ CUIDADO CRÍTICO OBSTETRICO» debe aplicarse solo a la unidad obstétrica? — consulta atenciones-11; dónde: `porcentaje_ocupacional.md › Observaciones › Estados numéricos; Regla CRIT amplia`.
12. **ATE-12** Vistas obstétricas: ¿TRIAGES OBSTÉTRICOS, OPORTUNIDAD TRIAGE OBSTÉTRICO, CONSULTAS OBSTÉTRICAS, OBSERVACIONES OBSTÉTRICAS y el botón de obstetricia de TRIAGE se limitan a las clasificaciones de triage terminadas en «-G»? ¿Qué regla de triage I está vigente? — consulta atenciones-05; dónde: `triages_obstetricos.md, oportunidad_triage_obstetrico.md, consultas_obstetricas.md, observaciones_obstetricas.md › Filtro obstétrico; triage.md › Reglas › Vista obstetricia`.
13. **ATE-13** En HOSPITALIZACIÓN PARCIAL y SES EN TU HOGAR, ¿el segmentador DIAGNÓSTICO usa CIE10, CMD o GRD? — dónde: `hospitalizacion_parcial.md / ses_en_tu_hogar.md › Observaciones › Campo del filtro de diagnóstico`.
14. **ATE-14** Sin año seleccionado, las tarjetas de promedio y proyección usan el año cerrado anterior y algunas tarjetas de total suman todos los años (SES EN TU HOGAR, CIRUGÍAS, CONSULTAS AMBULATORIAS, HOSPITALIZACIÓN PARCIAL). ¿Es el comportamiento deseado? — dónde: `cirugias.md › Proyección sin año seleccionado; ses_en_tu_hogar.md › Tarjeta ATENCIONES; consultas_ambulatorias.md › Proyección con bases distintas; Precedencia en Promedio_Dinamico; hospitalizacion_parcial.md › Medidas no documentadas`.
15. **ATE-15** Varios visuales muestran otro periodo que las tarjetas (torta de TRIAGE, mapa y anillo de TIPO LABORATORIO PATOLOGICO, mapa de árbol de ESPECIALIDAD IMAGENES, gráficos de QUIMIOTERAPIA y RADIOTERAPIA, torta de TRIAGES OBSTÉTRICOS). ¿Deben seguir al segmentador de año? — dónde: `triage.md › Torta con otro periodo; tipo_laboratorio_patologico.md › Mapa y anillo; especialidad_imagenes.md › Mapa de árbol sin año; quimioterapia.md / radioterapia.md › Años del gráfico; triages_obstetricos.md › Total distinto a la torta`.
16. **ATE-16** ¿El total de PARTOS excluye todos los tipos que no son parto (ABORTO, IVE, IVE EXTRA INSTITUCIONAL e IVE EXTRAINSTITUCIONAL)? ¿Cuáles son los visuales rotos de ABORTOS y PARTOS? — dónde: `partos.md › Observaciones › Tipos que no son parto; Visuales rotos; abortos.md › Observaciones › Visuales rotos`.
17. **ATE-17** REFERENCIA Y CONTRARREFERENCIA y MOTIVOS DE NO ACEPTACIÓN: ¿se cuentan solicitudes distintas o filas (una solicitud con varias causas se repite)? ¿MOTIVOS filtra solo el estado No Aceptado y la causa mayoritaria es de verdad un motivo de no aceptación? — consulta atenciones-10; dónde: `referencia_y_contrarreferencia.md › Indicadores › Solicitudes; Posibles duplicados; motivos_de_no_aceptacion.md`.
18. **ATE-18** UNIDAD CARDIONEUROVASCULAR: ¿el gráfico muestra la cantidad mensual ([CANT_ATENCIONESUCAR]) o el promedio ([PROM_ATENCIONESUCAR])? ¿Qué versión de las medidas está vigente? ¿El código CUPS de 6 dígitos que se ve en ESPECIALIDADES CARDIOVASCULAR es correcto? — dónde: `unidad_cardioneurovascular.md › Observaciones; especialidades_cardiovascular.md › Código CUPS sospechoso`.
19. **ATE-19** CONSULTAS SIN TRIAGE: ¿el gráfico cuenta todos los ingresos de urgencias o solo los sin triage? ATENCIONES PEDIÁTRICAS TRIAGE: ¿gráfico y torta filtran menores de edad? LABORATORIO: ¿qué medida usa el gráfico y cuál la tabla (no cuadran)? — dónde: `consultas_sin_triage.md › Gráfico frente a porcentaje; atenciones_pediatricas_triage.md › Valores que no cuadran; laboratorio.md › Gráfico y tabla no cuadran`.
20. **ATE-20** CONSULTAS PRIORITARIAS: ¿por qué las dos tarjetas salen «(En blanco)»? (la tarjeta del PBIR usa [PROMEDIO_MENSUAL]). ¿Las consultas de URGENCIAS, ATENCIONES PEDIÁTRICAS CONSULTAS y CONSULTAS OBSTÉTRICAS deben seguir mostrando 2023 y 2024? — consulta atenciones-06; dónde: `consultas_prioritarias.md › Tarjetas en blanco; urgencias.md / consultas_obstetricas.md / atenciones_pediatricas_consultas.md › Consulta desactualizada`.
21. **ATE-21** ¿Hay meta o semáforo (en minutos) para la oportunidad del triage y de la consulta de urgencias? De los dos documentos de OPORTUNIDAD TRIAGE, ¿cuál está vigente? — dónde: `oportunidad_triage.md › Observaciones › Sin meta; Dos documentos; oportunidad_urgencias.md › Sin meta`.

### Páginas, navegación y mantenimiento

22. **ATE-22** Las relaciones por OID de IMAGENES_CARDIOLOGIA, IMAGENES_ECOGRAFIA, IMAGENES_OTRAS y CIRUGIAS con ASEGURADORAS, CAMAS y UNIDAD, y la de SERVICIO con ASEGURADORAS (uno a uno), unen columnas OID que no son la aseguradora ni la cama. ¿Se eliminan? — consulta atenciones-04; dónde: `_diccionario.md › Relaciones (8 entradas)`.
23. **ATE-23** ¿El área GENARESER = 108 de QUIMIOTERAPIA es la misma que GASCODIGO = 108 de UNIDAD_CARDIOVASCULAR? — dónde: `_diccionario.md › Observaciones › Código de área 108`.
24. **ATE-24** Páginas de la documentación que no aparecen con ese nombre en el PBIP: ATENCIONES PEDIÁTRICAS CONSULTAS, ATENCIONES PEDIÁTRICAS TRIAGE, GINECO, MOTIVOS DE NO ACEPTACIÓN, % OCUPACIONAL, REFERENCIA Y CONTRARREFERENCIA y PACIENTES OBSERVADOS (¿es ATENCIONES PEDIATRICAS OBSERVACIONES?). ¿Cómo se llaman en Power BI y desde qué botón se llega? ¿QUIMIOTERAPIA y RADIOTERAPIA se abren desde CANCEROLOGÍA de INDICADORES? ¿ESPECIALIDAD IMAGENES es la «AREA DE SERVICIO IMAGENES» de la documentación? — dónde: `Observaciones › Nombre de página y Propósito (desde qué botón se llega) de esas páginas`.
25. **ATE-25** Páginas sin visuales ni documentación: ATENCIONES PEDIATRICAS OBSERVACIONES, DISTRIBUCION DE ATENCIONES EN UNIDAD NEUROCARDIOVASCULAR, Duplicado de DETALLE ESPECIALIDADES, Página 1, PROMEDIO ESTANCIA y TIPO LABORATORIO. ¿Se usan (y qué muestran) o se eliminan? — dónde: `nombre_funcional, Propósito y Observaciones › Bloque deducido de esas páginas`.
26. **ATE-26** ¿Qué hace el botón PUERTA de INDICADORES (los marcadores de servicio filtran FACT_EGRESOS[EGRESO_PUERTA])? ¿A dónde lleva el último botón de vista de OPORTUNIDAD URGENCIAS y el botón Detalle de LABORATORIO? ¿Qué medida y filtros usa el medidor de consulta general de DETALLE ESPECIALIDADES? — dónde: `indicadores.md › Visuales › Botón PUERTA; oportunidad_urgencias.md › Botones de vista; laboratorio.md › Botón Detalle; detalle_especialidades.md › Medidor general`.
27. **ATE-27** ¿Se pueden retirar las tablas sin uso Hoja1, UNIDAD CARDIONEUROVASCULAR, IMAGENES_CARDIOLOGIA, IMAGENES_ECOGRAFIA, IMAGENES_OTRAS y VistaServicios? — dónde: `_diccionario.md › Observaciones › Tablas sin uso aparente; Tablas › VistaServicios`.
28. **ATE-28** ¿Quién actualiza el libro DATOS EPIDEMIOLOGIA.xlsx (históricos mensuales) y el archivo de gestantes «partos MSPS», y con qué frecuencia? — dónde: `_diccionario.md › Observaciones › Pendientes de negocio; _general.md › Históricos mensuales`.

## BRIEFING HOSPITALARIO

### Afecta una tarjeta o un indicador visible

1. **BRI-1** En DETALLE NEDOCS, ¿las variables C (espera de consulta) y D (espera de cama) de GH_NEDOCS se registran en horas o en minutos? La fórmula del modelo usa los coeficientes estándar (5,64 y 0,93), que suponen horas. — consulta briefing-03; dónde: `detalle_nedocs.md › Indicadores › C espera de consulta / D espera de cama; _diccionario.md › Observaciones › Unidades de NEDOCS`.
2. **BRI-2** La tarjeta CONSULTAS URGENCIAS cuenta solo los triages de ayer clasificados I, II o III (CONSULTAS_REALIZADAS = 0); los IIP, IIS y IIIU quedan fuera. ¿Ese es el criterio correcto de «consulta de urgencias»? — dónde: `_diccionario.md › Observaciones › CONSULTAS_REALIZADAS`.
3. **BRI-3** En %OCUPACION de GESTIÓN CAMAS el numerador (camas ocupadas) incluye las camas de expansión (EXP) y OH, que el denominador excluye. ¿Es intencional (sí/no)? — dónde: `gestion_camas.md › Observaciones › Numerador de ocupación sin exclusiones`.
4. **BRI-4** EGRESOS EFECTIVOS HOY: si el ingreso tiene epicrisis de otro día y orden de salida de hoy, cuenta 0. ¿Debe contar como egreso efectivo (sí/no)? — dónde: `egresos_probables.md › Observaciones › Caso con epicrisis y orden`.
5. **BRI-5** La tarjeta IMAGENES TOMADAS cuenta servicios (filas) y no suma la cantidad (SERCANTID). ¿Debe sumar la cantidad? — dónde: `imagenes_diagnosticas.md › Observaciones › Conteo de imágenes`.
6. **BRI-6** La página OCUPACIÓN POR ESTANCIA no está en el PBIP y su tabla PACIENTES POR ESTANCIA ya no existe en el modelo. ¿Se retiró la página (sí/no)? Si sí, se elimina su documentación. — dónde: `ocupacion_por_estancia.md (Indicadores y Observaciones)`.

### Columnas, visuales y reglas

7. **BRI-7** En DETALLE OCUPACIÓN ColorFila pinta amarillo desde 4 días de estancia, pero la leyenda empieza en 6. ¿El umbral correcto es 4 o 6 días? — dónde: `detalle_ocupacion.md › Observaciones › Semáforo y leyenda no coinciden`.
8. **BRI-8** ¿La tarjeta A2 de NEDOCS («CAMAS EN EL SERVICIO DE URGENCIAS») es el total de camas de urgencias o las disponibles? — dónde: `detalle_nedocs.md › Observaciones › Descripción de A2`.
9. **BRI-9** ¿Qué significan las siglas SAMYL (alistamiento de camas), OH (camas excluidas de la ocupación), CAMA ACV / ruta ACV (12 camas fijas) y PAS y PCG (tipos de convenio)? — dónde: `_diccionario.md › Observaciones › Siglas; _general.md › Sigla OH; gestion_de_camas.md › SAMYL; gestion_camas.md › Marcador CAMAS_ACV; convenios.md › Siglas PAS y PCG`.
10. **BRI-10** ¿Qué regla calcula MOSTRAR_6TO en la vista CAMAS_DISPONIBLES (las camas con 0 se excluyen de la ocupación)? — consulta briefing-05; dónde: `gestion_camas.md › Observaciones › Columna MOSTRAR_6TO; _diccionario.md › Observaciones › Vistas de origen`.
11. **BRI-11** Nombres de los estados usados como filtro: solicitud de cama (estados 2, 3, 4, 5 y 8), recepción (OidEstado 7), remisión (EstadoOid 1 y EstadosRecOid 4) y solicitud y historial del briefing (1, 2, 3). ¿Puede indicar el nombre de cada uno o la tabla de Dinámica/PLANILLAUSUARIO que los describe? — dónde: `solicitud_camas.md, seguimiento_recepcion.md, seguimiento_remisiones.md, detalle_briefing.md › Observaciones › Significado de estados`.
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
2. **FIN-2** Ingresos abiertos: la tarjeta de COMPARATIVO usa TOTAL_ING_ABIERTOS (valor entidad + valor paciente) y la de INICIO usa VLSERVICIO. ¿Cuál es el valor oficial de ingresos abiertos? — consulta financiera-06; dónde: `comparativo.md › Observaciones › Ingresos abiertos con dos columnas`.
3. **FIN-3** ¿Con qué regla calcula la consulta de origen el costo estimado ANALISIS_RENTABILIDAD[COSTOVARIACION] (columna «Estimado» de COSTO ESTIMADO)? — dónde: `costo_estimado.md › Indicadores › Costo estimado; _diccionario.md › ANALISIS_RENTABILIDAD[COSTOVARIACION]`.

### Columnas, visuales y reglas

4. **FIN-4** ¿El %PARTICIPACIÓN del gráfico de aseguradores de INICIO debe calcularse sobre los 10 aseguradores visibles o sobre el total? — dónde: `inicio.md › Observaciones › Participación entre los 10 primeros`.
5. **FIN-5** ¿Qué es un «ingreso abierto» (qué estados de ingreso cuentan) y qué significa «ACTUAL» en INGRESOS ABIERTOS ACTUAL: corte a hoy o solo el mes en curso? — dónde: `_general.md › Definiciones › Ingresos abiertos; ingresos_abiertos_actual.md`.
6. **FIN-6** El segmentador MOSTRAR MEDICAMENTOS de CUPS: ¿arranca con los medicamentos incluidos o excluidos? — consulta financiera-01; dónde: `cups.md › Observaciones › Valores de mostrar medicamentos`.

### Páginas, navegación y mantenimiento

7. **FIN-7** ¿Se retira la medida [Prueba CostoUnitario] (columna con nombre técnico) de Duplicado de Duplicado de COSTOS X MESES? — dónde: `_diccionario.md › Observaciones › Medida de prueba`.
8. **FIN-8** COMPARATIVO, FACTURACIÓN GENERAL, Duplicado de FACTURACIÓN GENERAL, COSTOS X MESES, Duplicado de Duplicado de COSTOS X MESES y COSTOS ANTERIOR no se alcanzan desde INICIO. ¿Se eliminan (sí/no, por página)? — dónde: `_general.md › Observaciones › Páginas sin acceso`.
9. **FIN-9** ¿Se renombra «Duplicado de Duplicado de FACTURACIÓN GENERAL» (la página en uso) a FACTURACIÓN GENERAL? — dónde: `duplicado_de_duplicado_de_facturacion_general.md › Observaciones › Nombre de copia`.
10. **FIN-10** COSTO ESTIMADO filtra años fijos y no muestra 2026. ¿Se agrega 2026? — consulta financiera-07; dónde: `costo_estimado.md › Observaciones › Gráficos sin 2026`.
11. **FIN-11** En COSTOS ANTERIOR el %RENT de las filas se suma; ¿debe promediarse? — dónde: `costos_anterior.md › Observaciones › Porcentaje sumado`.
12. **FIN-12** ¿Las líneas de promedio de ANALISIS DE RENTABILIDAD y COSTO ESTIMADO (sobre VLRSERVICIOENORDEN, TOTAL_COSTO y RENTABILIDAD_TOTAL) se muestran a propósito? — dónde: `analisis_de_rentabilidad.md / costo_estimado.md › Observaciones › Promedios sobre otras columnas`.

## TABLERO CVC

### Afecta una tarjeta o un indicador visible

1. **CVC-1** ¿Qué cuenta la tarjeta TOTAL PRODUCTOS: registros de compra, productos distintos o solo los registros AUMENTÓ (en la captura coincide con estos, 4.367)? — consulta cvc-01; dónde: `cvc.md › Indicadores › Total productos; Observaciones › Total productos igual a aumentos`.
2. **CVC-2** ¿Las tarjetas TOTAL COMPRAS CON AUMENTO y CON DISMINUCIÓN son la suma de COMPRA_TOTAL (cantidad × último costo) de los registros con ESTADO AUMENTÓ y DISMINUYÓ? — consulta cvc-01; dónde: `cvc.md › Indicadores › Total compras con aumento / con disminución`.
3. **CVC-3** El gráfico TENDENCIA DE COSTOS se rotula «Desviación estándar» (%). ¿Es la desviación estándar de variacion_porcent por mes u otra columna? (el modelo no tiene esa medida y el PBIP no trae los visuales) — dónde: `cvc.md › Indicadores › Desviación de la tendencia de costos`.

### Columnas, visuales y reglas

4. **CVC-4** Un producto sin costo anterior queda con ESTADO AUMENTÓ (la resta usa 0) y, si el costo anterior es ≤ 1, la variación se mide contra el costo promedio. ¿Debe quedar sin estado (o como primera compra) en ese caso? — dónde: `cvc.md › Observaciones › Primera compra como aumento; _diccionario.md › Observaciones › Base del costo anterior`.
5. **CVC-5** En COSTOS_VARIACION el costo anterior es el mayor costo distinto del último, no el inmediatamente previo. ¿Es la intención? — dónde: `_diccionario.md › Observaciones › Costo anterior en COSTOS_VARIACION`.
6. **CVC-6** ¿Qué cuenta como «producto regulado» en la columna REGULADO del Excel de regulados, y qué contiene COSTOS_PRODUCTOS[REGULADO] (columna calculada sin fórmula)? — consulta cvc-02; dónde: `cvc.md › Observaciones › Producto regulado; _diccionario.md › Observaciones › Columna REGULADO sin cálculo`.

### Páginas, navegación y mantenimiento

7. **CVC-7** ¿Quién actualiza el Excel «Regulados y No Regulados Dinamica Gerencial» y cada cuánto? — dónde: `_diccionario.md › Observaciones › Fuente de regulados`.
8. **CVC-8** ¿Qué significa la sigla CVC y qué almacén es el código 062? — dónde: `_general.md › Observaciones › Sigla CVC, Almacén 062; _diccionario.md › Observaciones › Sigla y almacén`.

## DEMANDA INSATISFECHA

### Afecta una tarjeta o un indicador visible

1. **DEM-1** Camas: DEMANDA_INS (tarjeta HOSPITALIZACIÓN y NO ASIGNADAS) toma las solicitudes con EstadoOid = 4 y TOTAL_SOLICITUD_CAMAS las de EstadoOid distinto de 4. ¿Qué significa el estado 4 y cuál de las dos reglas es la correcta? — consulta demanda-01; dónde: `_diccionario.md › SOLICITUD DE CAMAS[DEMANDA_INS]; Reglas de cama distintas; solicitud_camas.md › Dos reglas de cama; consolidado.md › Reglas de cama distintas`.
2. **DEM-2** Triages: la página TRIAGES filtra TRIAGE[HCCESTADO] = 2 y CONSOLIDADO no. ¿Qué es el estado 2 y debe aplicarse también en CONSOLIDADO (sí/no)? ¿Qué son los conceptos HCNCONCOTRI 1 a 7 incluidos? — consulta demanda-02; dónde: `_diccionario.md › TRIAGE[HCCESTADO]; Triages: filtro solo en su página; triages.md › Clasificaciones incluidas / Filtro de página; consolidado.md › Triages sin filtro de estado`.
3. **DEM-3** Cirugías: el denominador de oportunas (CIRUGIAS REALIZADAS) incluye todas las solicitudes planeadas, no solo las operadas, y una solicitud cancelada tras más de 45 días cuenta como demanda insatisfecha. ¿Ambas reglas son correctas (sí/no cada una)? — dónde: `_diccionario.md › Cirugías realizadas; consolidado.md › Cirugías realizadas; cirugias.md › Cirugías canceladas`.

### Columnas, visuales y reglas

4. **DEM-4** Citas: ¿qué significa CCMESTADO = 1 en citas con causa de cancelación? — consulta demanda-03; dónde: `citas.md › Observaciones › Estado de la cita; Reglas de negocio › Causas incluidas`.
5. **DEM-5** SOLICITUD DE CAMAS une HPNSUBGRU por d.OID = a.serviciooid (OID del subgrupo igual al servicio solicitante). ¿Es correcta esa unión o el nombre de subgrupo puede salir equivocado? — dónde: `solicitud_camas.md › Observaciones › Unión de subgrupo`.

### Páginas, navegación y mantenimiento

6. **DEM-6** Los promedios mensuales incluyen el mes en curso incompleto. ¿Debe excluirse (sí/no)? — dónde: `_general.md › Observaciones › Promedios con el mes actual`.
7. **DEM-7** La documentación salta la página 6 y la tabla CONTRAREFERENCIA y la medida PROM_TRAMITES_CONTRA no tienen página. ¿Existía una página de contrarreferencia? ¿Se agrega o se retiran esa tabla y medida? — dónde: `_general.md › Observaciones › Página 6 ausente`.

## TABLERO CONTROL FACTURACION

### Afecta una tarjeta o un indicador visible

1. **CFA-1** PROCESO FACTURACION: «Egresos gestionados» ¿es el conteo distinto de ingresos? «Total facturado» ¿suma MONTO_FACTURADO de FACTURACION PERFILES? «Gestiones» ¿cuenta filas o suma? (la página no está en el PBIP local) — dónde: `proceso_facturacion.md › Indicadores`.
2. **CFA-2** El gráfico «Tiempo entre el egreso del paciente y la prefactura» mide de la entrega de ESTACION DE ENFERMERIA a la entrega de FACTURADOR SERVICIO. ¿Se cambia el título o el cálculo para que parta del egreso? — dónde: `_diccionario.md › Observaciones › TIEMPO_PREFACTURA; tiempos.md › Observaciones › Egreso o entrega; _general.md › Tiempo de egreso a prefactura`.

### Columnas, visuales y reglas

3. **CFA-3** ¿Qué significa el estado de ingreso AINESTADO = 4 en Dinámica? (0 registrado, 1 facturado, 2 anulado y 3 bloqueado ya están confirmados) — consulta control_facturacion-01; dónde: `_diccionario.md › ULT_GESTION[AINESTADO]; _general.md › Códigos AINESTADO`.
4. **CFA-4** ¿Qué marca ADNEGRESO.AEEGRCORCU = 1 (egresos que FACTURACION PENDIENTE excluye)? — dónde: `facturacion_pendiente.md › Reglas de negocio › Exclusión de egresos`.
5. **CFA-5** Los tiempos de FACTURACION PERFILES se calculan con fechas sin hora (siempre múltiplos de 24 h). ¿Se quiere precisión por hora? — dónde: `_diccionario.md › Observaciones › Horas múltiplos de 24`.
6. **CFA-6** FACTURACION PENDIENTE une TFACTURACI por el OID del ingreso y las demás consultas por el consecutivo (AINCONSEC). ¿Cuál es la llave correcta? — dónde: `facturacion_pendiente.md › Observaciones › Llave de trazabilidad`.
7. **CFA-7** FACTURACION PENDIENTE filtra HOSPITALARIO a nivel de página: ¿se quita el filtro o se quita el botón AMBULATORIO? — consulta control_facturacion-02; dónde: `facturacion_pendiente.md › Observaciones › Botón AMBULATORIO`.
8. **CFA-8** Los segmentadores AREA SERVICIO de FACTURADORES y RESUMEN FACTURACION no filtran (son de ULT_GESTION). ¿Se cambian a la columna de la tabla de la página? — dónde: `facturadores.md › Observaciones › Segmentador de área`.
9. **CFA-9** En EN PROCESO AUDITORIA MEDICAMENTOS los filtros se contradicen; ¿cuál es el filtro correcto? Y en las páginas EN PROCESO, la tabla «DIFERENCIA DE DIAS DESDE FECHA SALIDA PACIENTE» mide desde FECHA_RECIBE: ¿se corrige el título o el cálculo? — dónde: `en_proceso_*.md › Observaciones › Filtros contradictorios; Título de la tabla de diferencia`.

### Páginas, navegación y mantenimiento

10. **CFA-10** En las consultas de tiempos la auditoría se liga a los perfiles 4 o 5 por el usuario que entrega; ¿un mismo usuario puede trabajar en ambos perfiles (duplicaría filas)? ¿Y un ingreso con varias facturas debe contarse una vez en PROCESO FACTURACION? — dónde: `_general.md › Observaciones › Auditor por usuario; proceso_facturacion.md › Observaciones › Unión de facturas; inicio.md › Observaciones › Unión de auditorías`.
11. **CFA-11** ¿Cuál es el nombre en Power BI de las páginas AUDITORES EXTERNOS y PROCESO FACTURACION, y qué filtro de página tiene AUDITORES EXTERNOS? — consulta control_facturacion-03; dónde: `auditores_externos.md › Propósito y Reglas de negocio; proceso_facturacion.md › Propósito`.
12. **CFA-12** «Duplicado de INICIO» (versión de trabajo de PROCESO FACTURACION, con la columna rota SFANETOFAC) y TRAZABILIDAD FACTURACION (sin botón de entrada) ¿siguen en uso o se eliminan? — dónde: `duplicado_de_inicio.md; proceso_facturacion.md › Sin página en el PBIP; trazabilidad_facturacion.md › Sin botón de entrada`.

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

## TABLERO EPS

### Afecta una tarjeta o un indicador visible

1. **EPS-1** La tarjeta Ocupación de urgencias incluye el servicio SEXTO PISO y excluye las camas con «EXP» en el código. ¿SEXTO PISO cuenta como urgencias? ¿Qué son las camas EXP (¿expansión?) y deben excluirse? — consulta eps-02; dónde: `_diccionario.md › %OCUPACIONAL[codcama]; Observaciones › Ocupación de urgencias incluye SEXTO PISO; triages_atendidos.md › Ocupación de urgencias`.
2. **EPS-2** [%ATENDIDOS] divide atendidos por llegadas + pendientes acumulados, y los pendientes ya incluyen los de la hora. ¿Es el denominador deseado? — dónde: `_diccionario.md › Observaciones › Denominador de [%ATENDIDOS]; atenciones_admisiones.md`.

### Columnas, visuales y reglas

3. **EPS-3** El porcentaje de atenciones frente a admisiones cruza solo por documento y supera el 100 % (107,48 % en la captura). ¿Se acepta o se cambia el cruce? — dónde: `_diccionario.md › Observaciones › Porcentaje de atenciones frente a admisiones; atenciones_admisiones.md › Cruce solo por documento`.
4. **EPS-4** CONSULTAS PRIORITARIAS no corresponde a triages 4 y 5: ¿cuál es el rótulo correcto? ¿Por qué se excluyen los documentos 30 a 39 y las uniones que pueden dejar citas por fuera son intencionales? — dónde: `_diccionario.md › Consultas prioritarias no son triages 4 y 5; consultas_prioritarias.md`.
5. **EPS-5** ¿Cuál es el nombre del área de servicio 42 (el comentario de la consulta dice «42=ginecop…»)? — consulta eps-01; dónde: `_diccionario.md › Observaciones › Tipos de ingreso`.

### Páginas, navegación y mantenimiento

6. **EPS-6** ATENCIONES_GINECO (ingresos por maternidad) no la usa ninguna página: ¿se retira? — dónde: `_diccionario.md › Observaciones › ATENCIONES_GINECO sin uso visible`.

## TABLERO NAOS

### Afecta una tarjeta o un indicador visible

1. **NAO-1** ¿Qué criterios usa la vista TABLERO_NAOS para que un paciente aparezca en LISTADO (tarjeta PACIENTES) y cómo asigna TIPO_PACIENTE (incluido PACIENTE PRIORIZADO) y SOLICITUD_CAMA? — consulta naos-01; dónde: `_general.md › Observaciones › Vista sin documentar; listado.md › Observaciones › Clasificación sin documentar; _diccionario.md › Observaciones › Vista TABLERO_NAOS`.
2. **NAO-2** CIRUGÍAS PENDIENTES no filtra por fecha ni egreso. ¿Debe incluir pacientes ya egresados o ambulatorios? — dónde: `cirugias_pendientes.md › Observaciones › Sin filtro de fecha ni de egreso`.

### Columnas, visuales y reglas

3. **NAO-3** ¿Qué estado de la solicitud de cirugía es el 4 y qué tipo de cirugía es TipoCirugiaOid = 1 (¿programada?)? — dónde: `cirugias_pendientes.md › Observaciones › Estado 4 sin nombre, Tipo de cirugía 1`.
4. **NAO-4** GESTION CLINICA excluye solicitudes en estados 4, 5, 6 y 12, incluye la categoría 404 y no filtra HCAESTADO (la documentación solo menciona el estado 4). ¿Qué significan esos estados y el estado 3 del historial, y cuál es la regla vigente? — dónde: `gestion_clinica.md › Observaciones › Significado de estados; _diccionario.md › Observaciones › Consulta de gestión clínica distinta de la documentación`.
5. **NAO-5** En EXAMENES, ¿la tabla debe ocultar los ingresos sin exámenes pendientes? ¿Qué valores de ESTADO_EXAMEN existen además de PENDIENTE? — consulta naos-02; dónde: `examenes.md › Observaciones › Filas sin pendientes, Consulta de EXAMENES_NAOS`.

### Páginas, navegación y mantenimiento

6. **NAO-6** ¿Qué significa la sigla NAOS? — dónde: `_general.md › Observaciones › Significado de NAOS`.

## TABLERO PERFIL DE MORBILIDAD

### Afecta una tarjeta o un indicador visible

1. **MOR-1** Las tarjetas Egresos (INICIO) y Atenciones (FACTURACION, PERFIL DE MORBILIDAD) ¿cuentan filas de MATRIZ 2024 o ingresos distintos (MATRIZ 2024[Ingreso])? — consulta morbilidad-02; dónde: `inicio.md › Indicadores › Egresos; facturacion.md y perfil_de_morbilidad.md › Indicadores › Atenciones`.
2. **MOR-2** ¿El «Promedio de facturación» de FACTURACION es por factura (AVERAGE de VALOR_FACTURA) o por atención (total facturado / egresos)? — consulta morbilidad-03; dónde: `facturacion.md › Indicadores › Promedio de facturación`.

### Columnas, visuales y reglas

3. **MOR-3** El botón ONCOLOGICO de INICIO ¿filtra con ONCOLOGICO[ONCOLOGICO], MATRIZ 2024[ONCOLOGICOM] o MATRIZ 2024[P_ONCOLOGICO]? — dónde: `inicio.md › Observaciones › Columna del botón oncológico; _diccionario.md › Observaciones › Marca oncológica dispersa`.
4. **MOR-4** Los botones de servicio de INICIO ¿usan MATRIZ 2024[SERVICIOS] o Servicio_Agrupado? ¿Las barras usan GRD_R, CMD_R y CIE10_R? — dónde: `inicio.md › Reglas de negocio › Botones de servicio; Ejes de diagnóstico`.
5. **MOR-5** Desde 2025 los egresos usan el identificador interno del ingreso y FACTURACION el consecutivo: ¿la facturación de 2025 en adelante se cruza bien o hay que corregir la llave? — consulta morbilidad-02; dónde: `facturacion.md › Observaciones › Cruce incompleto en 2025`.

### Páginas, navegación y mantenimiento

6. **MOR-6** FACTURACION PERIOPERATORIA: la consulta de PERIOPERATORIA tiene comentada la columna VALOR_FACTURA. ¿De dónde sale la facturación de esa página? — dónde: `facturacion_perioperatoria.md › Propósito`.

## TABLERO FARMACIA

### Afecta una tarjeta o un indicador visible

1. **FAR-1** En la captura la tarjeta MEDICAMENTOS VENCIDOS de INICIO sale «(En blanco)» y la página MEDICAMENTOS VENCIDOS muestra 88. ¿Cuál es el valor correcto que debe ver el usuario? — consulta farmacia-05; dónde: `inicio.md › Observaciones › Vencidos en blanco`.
2. **FAR-2** ¿Cómo calcula la vista PRODUCTOS_VENCIDOS_FARMACIA el campo «mes» (meses para vencer): diferencia de meses calendario o días/30? Las tarjetas usan mes ≤ 1 como «0-30 días». — consulta farmacia-03; dónde: `_diccionario.md › Columnas clave › VENCIMIENTO_PRODUCTOS[mes]; medicamentos_vencidos.md › Observaciones › Días frente a meses`.

### Columnas, visuales y reglas

3. **FAR-3** ¿El filtro ESTADO de SUMINISTROS PENDIENTES usa PENDIENTES_FARMACIA[PENDIENTE] (PENDIENTE/DISPENSADO) y la columna CONSECUTIVO es AINCONSEC (consecutivo del ingreso)? El PBIP no trae los visuales de esa página. — dónde: `_diccionario.md › PENDIENTES_FARMACIA[PENDIENTE]; suministros_pendientes.md › Observaciones › Campos por confirmar`.
4. **FAR-4** La oportunidad de dispensación cuenta horas hasta hoy para las órdenes nunca dispensadas, lo que infla los meses antiguos. ¿Deben excluirse las órdenes sin documento de suministro del promedio? — consulta farmacia-06; dónde: `oportunidad_dispensacion.md › Observaciones › Tendencia llamativa`.

### Páginas, navegación y mantenimiento

5. **FAR-5** El botón INVENTARIO lleva a «Duplicado de STOCK MINIMO» (sin visuales en el PBIP). ¿Es esa la página vigente de stock mínimo y qué columnas tiene su tabla? — dónde: `duplicado_de_stock_minimo.md › Observaciones › Página sin visuales; stock_minimo.md › Observaciones › Columnas por confirmar`.
6. **FAR-6** ¿Para qué está Consulta1 (SELECT * FROM DIM_UNIDAD) si ninguna relación, medida ni visual la usa? ¿Se puede retirar? — dónde: `_diccionario.md › Tablas › Consulta1; _general.md › Fuentes de datos › Consulta1`.

## TABLERO ANTIBIOTICOS

### Afecta una tarjeta o un indicador visible

1. **ANT-1** ¿HCCANTIDAD (la cantidad aplicada que suma la tarjeta TOTAL DOSIS SUMINISTRADAS y [Dosis_Diaria]) está en unidades de presentación (ampollas, viales, tabletas) o en mg? — consulta antibioticos-01; dónde: `_diccionario.md › Medidas › [TOTAL DOSIS SUMINISTRADAS], [Dosis_Diaria]`.
2. **ANT-2** La tarjeta «TOTAL DOSIS SUMINISTRADAS» suma cantidades (SUM de HCCANTIDAD). ¿Debe sumar cantidades o contar aplicaciones (una por administración)? — dónde: `_diccionario.md › Observaciones › Pendiente para el dueño`.

### Columnas, visuales y reglas

3. **ANT-3** ¿Qué representa HCCANTDOSIS: la dosis prescrita por aplicación (en la misma unidad que HCCANTIDAD) u otra cosa? — consulta antibioticos-01; dónde: `_diccionario.md › Columnas clave › ANTIBIOTICOS[hccantdosis]`.
4. **ANT-4** La consulta excluye HCAESTADO = 6 y toma solo HCRESPUES = 0. ¿Qué significan ese estado 6 y la respuesta 0 (¿orden anulada?, ¿aplicación sin respuesta/no rechazada?)? — dónde: `_general.md › Observaciones › Significado de códigos`.
5. **ANT-5** El estado ACTIVO se calcula como «unidades despachadas menos aplicadas > 0», no con la orden médica vigente. ¿Es el criterio correcto de paciente con tratamiento activo (tarjeta de pacientes activos)? — dónde: `_general.md › Observaciones › Estado ACTIVO por despacho`.

## TABLERO RECEPCION TECNICA

### Afecta una tarjeta o un indicador visible

1. **REC-1** La tarjeta TIEMPO PROMEDIO EN GESTION de PROMEDIO GESTION MENSUAL suma los promedios de todos los meses y estados (≈ 86) en lugar de promediarlos (las líneas están entre 0 y 7 días). ¿Debe mostrar el promedio? — dónde: `promedio_gestion_mensual.md › Observaciones › Escalas distintas; _diccionario.md › Observaciones › Suma de promedios`.
2. **REC-2** La tarjeta PEDIDO GESTIONADOS suma CANTIDAD_REGISTROS, que cuenta estados terminados y no pedidos distintos. ¿Debe contar pedidos distintos? — dónde: `_diccionario.md › Observaciones › Pedidos gestionados`.

### Columnas, visuales y reglas

3. **REC-3** TIEMPO_1 a TIEMPO_5 pueden salir negativos si las etapas se registran fuera de orden. ¿Las tarjetas y la tabla deben excluir esos registros? — dónde: `detalle_recepcion_tecnica.md / _diccionario.md › Observaciones › Tiempos entre etapas`.
4. **REC-4** PROMEDIO GESTION trae 6 meses y PROMEDIO GESTION MENSUAL desde el 1 de enero de 2025. ¿Cuál ventana es la vigente? — dónde: `_diccionario.md › Observaciones › Ventanas distintas`.
5. **REC-5** La consulta de CANTIDADES no filtra cantidad pendiente > 0 ni estado de la solicitud. ¿Cómo se limita a los pendientes (o debe agregarse ese filtro)? — dónde: `cantidades.md › Observaciones › Pendiente sin filtro explícito`.

## TABLERO REFERENCIA

### Afecta una tarjeta o un indicador visible

1. **REF-1** Las tarjetas de INICIO, DETALLE RECEPCIONES, DETALLE ACEPTADOS y DETALLE NO ACEPTADOS: «Cantidad de solicitudes» ¿cuenta REFERENCIA[OID] (distinto)? «Tiempo promedio de respuesta» ¿es el promedio (no la mediana) de TIEMPO_REMISION en horas? «Promedio de edad» ¿es el promedio de ANOS? — dónde: `inicio.md, detalle_recepciones.md, detalle_aceptados_recepcion.md, detalle_no_aceptados_recepcion.md › Indicadores`.
2. **REF-2** DETALLE REMISION: «Remisiones» ¿cuenta OidRemision distintos de CONTRARREFERENCIA? «Tiempo promedio de respuesta» ¿promedia TIEMPO_RESPUESTA en horas? — dónde: `detalle_remision.md › Indicadores`.

### Columnas, visuales y reglas

3. **REF-3** ¿Qué contiene CONTRARREFERENCIA[Expr3] (columna sin nombre de la vista SEGUIMIENTO_REMISIONES_DW) y CONTRARREFERENCIA[Nombre] es el estado de la remisión? — consulta referencia-01; dónde: `_diccionario.md › Columnas clave › CONTRARREFERENCIA[Expr3], [Nombre]`.
4. **REF-4** ¿Las solicitudes que no tienen respuesta (ni aceptadas ni no aceptadas) deben excluirse del tiempo promedio? ¿Por qué tantas solicitudes llegan sin especialidad? — consulta referencia-02; dónde: `_general.md › Observaciones › Solicitudes sin respuesta; inicio.md › Especialidad vacía`.

## TABLERO LAVANDERIA

### Afecta una tarjeta o un indicador visible

1. **LAV-1** ¿El peso de LAVANDERIA[Peso] (indicador principal) está en kilogramos o en libras? — consulta lavanderia-01; dónde: `pagina_1.md › Indicadores › Peso; _general.md › Definiciones › Peso`.

### Columnas, visuales y reglas

2. **LAV-2** ¿Los segmentadores Año y Mes filtran por Fecha (encabezado de la jornada) o por FechaRegistro (hora del pesaje)? — consulta lavanderia-02; dónde: `_diccionario.md › Columnas clave › LAVANDERIA[Fecha]; pagina_1.md › Observaciones › Fecha de los filtros`.

## Consultas DAX que no necesitan al propietario

Estas consultas resuelven con datos (agregados, valores de columnas no personales y rangos de fechas) dudas de dominio, unidad o vigencia. Se ejecutan en DAX Studio o con la API de consultas contra el modelo indicado; ninguna devuelve filas de pacientes.

| Id | Modelo | Qué resuelve |
|---|---|---|
| antibioticos-01 | TABLERO_ANTIBIOTICOS | Inferir la unidad de HCCANTIDAD y de hccantdosis: rango y valores típicos por antibiótico (si salen 1, 2, 3 son unidades/ampollas; si salen 500, 1000, 2000 son mg). |
| antibioticos-02 | TABLERO_ANTIBIOTICOS | Los 30 valores más frecuentes de HCCANTIDAD con su número de aplicaciones. |
| briefing-01 | BRIEFING HOSPITALARIO | Valores de AMBULATORIO_SS[TIPO_CONSULTA] (vista BI_PROXIMAS_CITAS) y cuántos días cubre la vista. |
| briefing-02 | BRIEFING HOSPITALARIO | Estados del trámite de remisión (catálogo, sin pacientes). |
| briefing-03 | BRIEFING HOSPITALARIO | Rango de las variables C y D de NEDOCS para saber si están en horas o en minutos (la fórmula estándar usa horas). |
| briefing-04 | BRIEFING HOSPITALARIO | Nombres de área de servicio que muestra el gráfico de imágenes tomadas. |
| briefing-05 | BRIEFING HOSPITALARIO | Qué marca CAMAS DISPONIBLES[MOSTRAR_6TO]: camas por valor y servicio (sin pacientes). |
| briefing-06 | BRIEFING HOSPITALARIO | Fechas que cubren las tablas de digiturnos, citas próximas, imágenes y convenios. |
| control_facturacion-01 | Tablero Control Facturacion | Estados de ingreso presentes en ULT_GESTION (¿aparece el 4?). |
| control_facturacion-02 | Tablero Control Facturacion | Pendientes por tipo de ingreso (si el botón AMBULATORIO puede mostrar algo). |
| control_facturacion-03 | Tablero Control Facturacion | Filas por perfil en FACTURACION PERFILES (si AUDITORES EXTERNOS y ESTACION ENFERMERIA tienen registros). |
| cvc-01 | TABLERO_CVC | Qué cuentan y suman las tarjetas: registros, productos distintos y COMPRA_TOTAL por ESTADO (comparar con la captura: TOTAL PRODUCTOS 4.367). |
| cvc-02 | TABLERO_CVC | Valores de la marca de regulación del Excel de regulados (y de la columna sin expresión COSTOS_PRODUCTOS[REGULADO]; si esta falla, quitarla). |
| cvc-03 | TABLERO_CVC | Hasta qué fecha llegan los registros de costo. |
| atenciones-01 | TABLERO DE ATENCIONES INSTITUCIONALES | Valores de primera vez/control, estado y tipo de atención de las citas ambulatorias (códigos, no pacientes). |
| atenciones-02 | TABLERO DE ATENCIONES INSTITUCIONALES | Tipos de laboratorio de patología y categoría EPS (catálogo). |
| atenciones-03 | TABLERO DE ATENCIONES INSTITUCIONALES | Periodo que cubre la parte histórica (AT_AMB_MAYO_2025, antes del 2025-11-01) de CONSULTAS_AMBULATORIAS y desde cuándo viene la parte actual. |
| atenciones-04 | TABLERO DE ATENCIONES INSTITUCIONALES | Comprobar las relaciones sospechosas por OID: cuántos OID distintos de cada tabla existen también en la tabla destino. |
| atenciones-05 | TABLERO DE ATENCIONES INSTITUCIONALES | Clasificaciones de triage (incluidas las obstétricas -G y el triage I) en las dos tablas de urgencias, con su conteo. |
| atenciones-06 | TABLERO DE ATENCIONES INSTITUCIONALES | Hasta qué fecha llega cada tabla de hechos (y si las consultas de urgencias ya no traen 2023 y 2024). |
| atenciones-07 | TABLERO DE ATENCIONES INSTITUCIONALES | De dónde puede salir la cifra de 308 camas de CAPACIDAD INSTALADA: conteos de camas en las tablas y medidas del modelo. |
| atenciones-08 | TABLERO DE ATENCIONES INSTITUCIONALES | Valor anual de cada medida de promedio de estancia, para ver cuál da el rango 118–148 de la captura y en qué unidad. |
| atenciones-09 | TABLERO DE ATENCIONES INSTITUCIONALES | Estados actuales de las solicitudes de cirugía (para definir pendientes y canceladas). |
| atenciones-10 | TABLERO DE ATENCIONES INSTITUCIONALES | Si una solicitud de referencia aparece en varias filas (una por causa): filas frente a solicitudes distintas, por estado. |
| atenciones-11 | TABLERO DE ATENCIONES INSTITUCIONALES | Servicios que caen en la regla CRIT de ocupación y códigos de estado de las camas habilitadas. |
| demanda-01 | Demanda Insatisfecha | Cuántas solicitudes de cama hay por EstadoOid y cuántas marca DEMANDA_INS, para ver qué regla de estado (=4 o <>4) cuadra. |
| demanda-02 | Demanda Insatisfecha | Triages por estado del turno (HCCESTADO) y por concepto (HCNCONCOTRI): cuánto cambia el total con y sin el filtro de estado 2. |
| demanda-03 | Demanda Insatisfecha | Código y nombre de las causas de cancelación de citas, y estado de la cita (catálogo, sin pacientes). |
| eps-01 | TABLERO EPS | Nombres de las áreas de servicio 2 y 42 (catálogo, no pacientes). |
| eps-02 | TABLERO EPS | Camas con EXP en el código y servicios a los que pertenecen (catálogo de camas). |
| farmacia-01 | TABLERO_FARMACIA | Nombres exactos de los almacenes (catálogo, no datos de pacientes). |
| farmacia-02 | TABLERO_FARMACIA | Áreas de servicio del filtro SERVICIO de OPORTUNIDAD DISPENSACIÓN y zonas de almacenamiento de los lotes. |
| farmacia-03 | TABLERO_FARMACIA | Cómo calcula la vista PRODUCTOS_VENCIDOS_FARMACIA el campo mes: días que faltan para vencer (mínimo y máximo) por cada valor de mes. |
| farmacia-04 | TABLERO_FARMACIA | Granularidad de VENCIMIENTO_PRODUCTOS: filas frente a combinaciones distintas de producto, lote, zona y almacén. |
| farmacia-05 | TABLERO_FARMACIA | Por qué la tarjeta MEDICAMENTOS VENCIDOS de INICIO puede salir en blanco: total de iddcantid y rango de fechas de PRODUCTOS_VENCIDOS por almacén. |
| farmacia-06 | TABLERO_FARMACIA | Peso de las órdenes sin dispensar en la oportunidad: promedio de OportunidadHor por mes con y sin documento de suministro. |
| financiera-01 | TABLERO_FINANCIERA | Valores de los dos campos de medicamentos de CUPS y si coinciden fila a fila. |
| financiera-02 | TABLERO_FINANCIERA | Valores de la marca de copago de la facturación diaria. |
| financiera-03 | TABLERO_FINANCIERA | Lista de clasificaciones de servicio de FACTU_AREA (catálogo, no datos de pacientes). |
| financiera-04 | TABLERO_FINANCIERA | Forma de los valores de COSTOS[CUP_ACTIVIDAD] (código de actividad y CUPS): cuántos hay y los 30 más frecuentes. |
| financiera-05 | TABLERO_FINANCIERA | Comparar por año la facturación de FACTURACION y de FACTU_AREA (base de [NETA] frente a [NETA_AREA] y de la tabla frente a la torta). |
| financiera-06 | TABLERO_FINANCIERA | Si TOTAL_ING_ABIERTOS (entidad + paciente) suma lo mismo que VLSERVICIO en FACTURACION_PENDIENTE. |
| financiera-07 | TABLERO_FINANCIERA | Hasta qué fecha llega cada tabla de hechos (y si COSTO ESTIMADO ya tiene datos de 2026). |
| lavanderia-01 | Tablero_lavanderia | Inferir la unidad del peso por su rango (un pesaje de ropa por servicio de decenas indica kg; de cientos, libras). |
| lavanderia-02 | Tablero_lavanderia | Rango de las dos fechas y cuántos pesajes caen en un día distinto del de su encabezado (si casi nunca difieren, da igual cuál alimenta Año y Mes). |
| naos-01 | TABLERO NAOS | Valores que entrega la vista TABLERO_NAOS para las marcas TIPO_PACIENTE (gráfico CLASIFICACIÓN) y SOLICITUD_CAMA, con conteo. |
| naos-02 | TABLERO NAOS | Valores posibles de EXAMENES[ESTADO_EXAMEN]. |
| morbilidad-01 | TABLERO PERFIL DE MORBILIDAD | Si una cirugía con varios procedimientos o varios GRD por diagnóstico repite filas en PERIOPERATORIA. |
| morbilidad-02 | TABLERO PERFIL DE MORBILIDAD | Egresos por año, ingresos distintos (duplicados por epicrisis) y cuántos cruzan con FACTURACION (cruce incompleto desde 2025). |
| morbilidad-03 | TABLERO PERFIL DE MORBILIDAD | Si FACTURACION tiene varias facturas por ingreso (promedio por factura frente a promedio por atención). |
| referencia-01 | TABLERO_REFERENCIA | Valores del estado de la remisión (CONTRARREFERENCIA[Nombre]) y forma de Expr3 sin listar sus valores (cuántos distintos, vacíos y largo máximo), porque Expr3 no está documentada y podría traer datos personales. |
| referencia-02 | TABLERO_REFERENCIA | Solicitudes sin especialidad (SERVICIO vacío) y sin respuesta, por mes, y rango de fechas de REFERENCIA y CONTRARREFERENCIA. |
| urgencias-01 | TABLERO TIEMPOS URGENCIAS | Cuántas consultas del día tienen los códigos IIP e IIS, que TRIAGE_II no cuenta. |
