---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: GENERAL
nombre_funcional: Indicadores asistenciales institucionales por servicio
bloque: General
tablas: [Calendario, TERCERO, ASEGURADORAS, DIM_SERVICIO, MostrarProyeccion, VistaServicios]
actualizado: 2026-10-20
version: 1
---

# GENERAL

## Propósito
Tablero histórico de la actividad asistencial del hospital: egresos, estancia, ocupación y giro cama en INICIO, y una página por servicio (triage, urgencias, imágenes, laboratorios, cirugías, obstetricia, consulta ambulatoria, hospitalización parcial, atención domiciliaria, oncología, referencia y otras). Compara meses entre años desde 2023. Se entra por INICIO; las páginas de detalle están ocultas y se abren con sus botones.

## Fuentes de datos
- **Origen de los datos**: Consultas SQL sobre la bodega institucional DWSES (tablas DIM_ y FACT_) que se alimenta del sistema de información Dinámica (base DGEMPRES10); algunas páginas leen vistas propias (ATC_DOMICILIARIA, CONSOLIDADO_IMAGENES_DWSES, fact_referencia).
- **Calendario**: Tabla de fechas calculada con CALENDAR desde 2023-01-01 hasta el 31 de diciembre del año en curso, con columnas AÑO, MES y AñoMes; filtra casi todas las páginas por Año y Mes.
- **TERCERO**: Terceros (aseguradores) con su nombre comercial TERNOMCOM; alimenta los segmentadores ASEGURADOR de INICIO, triage y cirugías.
- **ASEGURADORAS**: Planes de beneficio (GENDETCON) con su tercero; se relaciona con gineco, referencia, imágenes antiguas y estancia.
- **DIM_SERVICIO**: Servicios homologados (SERVICIO_HOMOLOGADO) que unen egresos, estancia y ocupación.
- **MostrarProyeccion**: Tabla fija con las opciones «SI» y «No» que alimenta las casillas «Mostrar proyección».
- **VistaServicios**: Tabla fija con IND_GEN, IND URG, IND GIN, IND NEO, IND HOSP e IND UCI; parece apoyar las vistas por servicio de INICIO. Por confirmar.
- **Históricos mensuales**: Tablas EGRESOS, EGRESOS_URGENCIAS, EGRESOS_GINECO, EGRESOS_NEONATOS, EGRESOS_UCI, CIRUGIAS_ARC, CONSULTA_AMBULATORIAS, ATENCIONES_IMAGENES, ATENCIONES_LABORATORIO y Hoja1 con totales por año y mes cargados de un archivo; se usan en proyecciones. Origen del archivo por confirmar.

## Definiciones
- **Clasificación de triage**: Códigos I, II, III, IV y V; los obstétricos llevan sufijo -G (I-G emergencia obstétrica, II-G urgencia médica obstétrica, III-G urgencia obstétrica, IV-G no urgente obstétrica, V-G consulta externa obstétrica).
- **Códigos de triage agrupados**: IIIU cuenta como III; IIP e IIS cuentan como II; M se muestra como MUERTO; el código UA se excluye de todas las consultas de triage.
- **Llegada (portero)**: Hora en que se registra la llegada del paciente (HCCFECTUR); si no existe, se usa la hora del triage.
- **Folio**: Registro de historia clínica; el primer folio del ingreso marca el inicio de la consulta médica.
- **Ingreso**: Admisión del paciente (AINCONSEC); su fecha es AINFECING.
- **Tipo de ingreso**: AINTIPING 1 es ambulatorio y 2 hospitalario.
- **Ingreso por urgencias**: AINURGCON 0 es urgencias y 1 consulta externa.
- **Causa de ingreso**: AINCAUING 1 enfermedad profesional, 2 heridos en combate, 3 enfermedad general adulto, 4 enfermedad general pediatría, 6 accidente de tránsito, 7 catástrofe FISALUD, 9 maternidad, 10 accidente laboral, 11 cirugía programada; otro valor es OTRA.
- **Áreas de servicio**: GENARESER 2 urgencias, 42 gineco-obstetricia, 15 laboratorio clínico, 108 quimioterapia y 117 radioterapia.
- **Estado de la cita**: CCMESTADO 0 asignada, 1 cancelada, 2 cumplida, 3 incumplida, 4 facturada y 5 inatención.
- **Grupo de edad**: MENORES DE EDAD si la edad es menor de 18 años; si no, MAYORES DE EDAD.
- **Categoría EPS**: Por el concepto de facturación del plan: 125 medicina prepagada, 126 póliza, 127 particular, 122 plan complementario y cualquier otro contributivo/subsidiada.
- **Año en curso y año cerrado**: Año en curso es YEAR(TODAY()); año cerrado es el anterior. Las medidas «dinámicas» muestran el año elegido en el segmentador y, si no hay año elegido, el año cerrado.
- **Proyección mensual**: Valor del mismo mes del año anterior multiplicado por (1 + crecimiento de ese mes entre los dos años anteriores); solo se dibuja con «Mostrar proyección» = SI.

## Reglas de negocio
- **Agrupación de aseguradoras**: Nombres con NUEVA se agrupan como NUEVA EPS; con SURA (sin ARL SURA, seguros de vida ni Suramericana) como SURA; con SANITAS (sin Colsanitas ni Medisanitas) como SANITAS; con MALLAMAS como MALLAMAS; el resto conserva su nombre.
- **Periodo cargado**: La mayoría de consultas traen datos desde 2023-01-01 hasta hoy; cada página indica su periodo cuando es distinto.
- **Ingresos excluidos**: Las consultas de urgencias excluyen los ingresos con AINESTADO 2 y 4. Significado de esos estados por confirmar.
- **Segmentadores comunes**: Casi todas las páginas tienen ASEGURADOR, Año y Mes; las de triage y urgencias agregan Día, grupo de edad y los botones GENERAL, URGENCIAS y OBSTETRICIA.
- **Navegación**: El botón de casa vuelve a INICIO y la flecha vuelve a la página anterior del grupo.

## Observaciones
- **PBIP parcial**: El PBIP disponible solo trae cinco páginas (INICIO sin page.json, CONSULTAS PRIORITARIAS, IMAGENES, LABORATORIO PATOLOGICO y DETALLE ESPECIALIDADES), todas ocultas en modo lectura; los nombres del resto de páginas salen de la documentación.
- **Medidas con año fijo**: Muchas medidas tienen el año escrito en la fórmula (TRIAGES_2025, OBSERVADOS_2025, IMG_2025, ATEN_DOM2025, ATEHP2025, ATE2025) y no siguen al segmentador de Año.
- **Nombres de medida engañosos**: PRIORITARIAS_2024 usa YEAR(TODAY()-1), que da el año en curso; PROMEDIO_TRIAGE_2024 filtra 2025 en el modelo.
- **Consultas desactualizadas**: Varias consultas SQL de la documentación no coinciden con las columnas del modelo (por ejemplo CONSULTA_URGENCIAS ya no tiene OID_TRIAGE ni TIEMPO_PARA_CONSULTA).
- **Documentos mal titulados**: El documento «SES en tu Hogar» se titula HOSPITALIZACIÓN PARCIAL y muestra esa página, pero su consulta y medidas son de atención domiciliaria; el de laboratorio clínico describe «imágenes».
- **Catálogo local**: Las fórmulas de medidas que no trae la documentación se tomaron del catálogo del modelo y se marcan «Por confirmar».

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
