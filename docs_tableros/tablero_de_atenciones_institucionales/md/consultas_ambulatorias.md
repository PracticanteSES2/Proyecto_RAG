---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: CONSULTAS AMBULATORIAS
nombre_funcional: Volumen y oportunidad de las consultas ambulatorias
bloque: Histórico
tablas: [CONSULTAS_AMBULATORIAS, CONSULTA_AMBULATORIAS, Calendario, MostrarProyeccion]
actualizado: 2026-10-20
version: 1
---

# CONSULTAS AMBULATORIAS

## Propósito
Muestra cuántas consultas ambulatorias (consulta externa) se atienden cada mes, compara los años con proyección opcional y presenta la oportunidad en días para consulta general, de control y de primera vez. Desde aquí se llega a DETALLE ESPECIALIDADES.

## Fuentes de datos
- **CONSULTAS_AMBULATORIAS**: Citas médicas desde 2025-11-01 con folio de historia clínica el mismo día, unidas a la tabla histórica AT_AMB_MAYO_2025 (periodo que cubre por confirmar). Trae asegurador, especialidad agrupada, médico, fechas de asignación y de cita, tipo de atención, primera vez o control y estado de la cita.
- **CONSULTA_AMBULATORIAS**: Totales históricos de atenciones ambulatorias por año y mes; la usa la proyección.

## Indicadores
- **Total consultas año anterior**: Consultas del año anterior. Medida por confirmar (la documentación lista AMB_ANT = CALCULATE(COUNT(CONSULTAS_AMBULATORIAS[OID_CITA]), YEAR(CONSULTAS_AMBULATORIAS[FECHA_CITA])=YEAR(TODAY())-1)).
- **Promedio mensual año anterior**: Consultas del año anterior divididas por sus meses. Medida por confirmar (en el modelo, Promedio Mensual Año Pasado).
- **Días de asignación de cita**: Días entre la fecha en que se asigna la cita y la fecha de la cita. Cálculo: promedio_asignacion = AVERAGE(CONSULTAS_AMBULATORIAS[DIAS_REAL]); DIAS_REAL = DATEDIFF(FECHA_ASIGNA_CITA, FECHA_CITA, DAY). Unidad: días.
- **Oportunidad dinámica**: Medida Promedio_Dinamico: con filtro de fecha muestra promedio_asignacion del filtro; sin filtro muestra el del último mes cerrado (mes anterior al actual).
- **Proyección de consultas**: Medida Proyeccion_Amb: consultas cumplidas del mismo mes del año anterior por (1 + variación frente al mismo mes de hace dos años); solo con «Mostrar proyección» = SI.

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes, ESTADO y ESPECIALIDAD.
- **Gráfico de consultas ambulatorias**: Líneas «CONSULTAS AMBULATORIAS» por mes, una línea por año y una de Proyeccion.
- **Medidores de oportunidad**: Tres medidores en días: «OPORTUNIDAD CONSULTA GENERAL» (máximo 20), «OPORTUNIDAD CONSULTA CONTROL» (máximo 20) y «OPORTUNIDAD CONSULTA PRIMERA VEZ» (máximo 15).
- **Tabla de detalle anual**: Matriz de consultas por año (filas) y mes (columnas).
- **Tarjetas de consultas**: «TOTAL CONSULTAS AÑO ANTERIOR» y «PROMEDIO MENSUAL AÑO ANTERIOR».
- **Botón Detalle especialidades**: Lleva a la página DETALLE ESPECIALIDADES; el botón de casa vuelve a INICIO.

## Reglas de negocio
- **Metas de oportunidad**: Columnas fijas GENERAL = 20, CONTROL = 20 y CONSULTA_PRA = 15 días; se usan como máximo de los medidores.
- **Exclusiones de citas**: Se excluyen citas canceladas, actividades prioritarias (nombre con PRIORI), citas sin folio y 11 especialidades por código interno.
- **Primera vez o control**: Se toma de la historia clínica; si no está, es «Primera Vez» cuando la actividad dice PRIMERA VEZ y «Control» en otro caso.
- **Estado de la cita**: 0 ASIGNADA, 1 CANCELADA, 2 CUMPLIDA, 3 INCUMPLIDA, 4 FACTURADA y 5 INATENCION.
- **Agrupación de especialidades**: Se agrupan hematología, cuidado paliativo, geriatría, neumología, rehabilitación pulmonar (espirometría, difusión con monóxido), rehabilitación cardiaca (test de caminata) y canguro (menores de 2 años). Anestesiología se divide en clínica del dolor (dos médicos específicos) y chequeo preanestésico; las variantes de «chequeo anestesia» del histórico se unifican.
- **Gastroenterología sin consulta**: Las actividades de gastroenterología que no son consulta quedan como GASTROENTEROLOGIA_QUITAR y se excluyen.
- **Una cita por día**: Si hay varios folios para el mismo asegurador, especialidad, paciente y fecha de cita, se toma el último.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Columna OID_CITA**: AMB_ANT y AMB_ACT cuentan OID_CITA, que no existe en el modelo; el modelo cuenta IDENTIFICACION.
- **Proyección con bases distintas**: Proyeccion_Amb toma el año anterior de CONSULTAS_AMBULATORIAS (solo cumplidas) y el de hace dos años de CONSULTA_AMBULATORIAS (totales históricos); por confirmar si son comparables.
- **Regla de obstetricia**: La agrupación OBSTETRICIA compara el nombre de la actividad con 'OBST' sin comodines, así que casi nunca aplica.
- **Precedencia en Promedio_Dinamico**: La condición mezcla || y && sin paréntesis; DAX evalúa primero el &&. Por confirmar la intención.
- **Etiquetas de tarjetas**: La documentación describe «total de consultas» y «promedio mensual», pero las tarjetas dicen «AÑO ANTERIOR».

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
