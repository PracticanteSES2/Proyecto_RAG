---
tablero: BRIEFING HOSPITALARIO
pagina: URGENCIAS
nombre_funcional: Comportamiento del servicio de urgencias del día anterior
bloque: Día
tablas: [TRIAGES]
actualizado: 2026-11-03
version: 3
---

# URGENCIAS

## Propósito
Resume la actividad del servicio de urgencias del día anterior: triages atendidos (generales y gineco), consultas de urgencias, consultas prioritarias, pacientes en observación y hospitalizados, con los triages por hora y el detalle de consultas prioritarias. Sirve para identificar picos de demanda y organizar el personal. Se llega desde el botón DETALLE URGENCIAS del visual TRIAGES por CLASIFICACIÓN en INICIO.

## Fuentes de datos
- **TRIAGES**: Triages del día anterior (DIM_TRIAGE) con clasificación, aseguradora, fecha y hora del triage, hora de llegada a portería, tramo horario, día de la semana y grupo de edad.
- **Otras tablas**: CONSULTAS URGENCIAS: triages de ayer (DIM_TRIAGE) sin código UA ni ingreso anulado (AINESTADO 2), con CONSULTAS_REALIZADAS = 0 para I, II y III y 1 para obstétricos y muerto. CONSULTAS PRIORITARIAS: citas de ayer cuyo tipo de actividad contiene PRIORITARIA, con estado 0 REGISTRADO, 1 ANULADO o 2 CONFIRMADO. PACIENTES OBSERVADOS y PACIENTES HOSPITALIZADOS: ingresos de ayer por urgencias (AINURGCON 0) en las áreas 2 y 42 (anotadas en la consulta como «2=urgencias 42=ginecop»), de tipo de ingreso 1 y 2 (AINTIPING) respectivamente.

## Indicadores
- **Triages atendidos**: Número de triages del día anterior. DISTINCTCOUNT(TRIAGES[OID_TRIAGE]) sin las clasificaciones que contienen MUERTO u OBSTETRICA (filtro del visual).
- **Triages gineco**: Triages con clasificación obstétrica (códigos terminados en -G). DISTINCTCOUNT(TRIAGES[OID_TRIAGE]) con TRIAGES[DESCRI_TRIGE] que contiene OBSTETRICA (filtro del visual).
- **Consultas urgencias**: Consultas médicas de urgencias. COUNT(CONSULTAS URGENCIAS[OID_TRIAGE]) con CONSULTAS_REALIZADAS = 0, es decir triages de ayer clasificados I, II o III (filtro del visual).
- **Consultas prioritarias**: Consultas por el canal de consulta prioritaria; muestra «(En blanco)» si no hay. COUNT(CONSULTAS PRIORITARIAS[GENPACIEN]) con ESTADO_NOMBRE que contiene CONFIRMADO o REGISTRADO (filtro del visual).
- **Pacientes observados**: Pacientes en observación de urgencias. DISTINCTCOUNT(PACIENTES OBSERVADOS[PACNUMDOC]).
- **Pacientes hospitalizados**: Pacientes de urgencias hospitalizados. DISTINCTCOUNT(PACIENTES HOSPITALIZADOS[PACNUMDOC]) sin el área UNIDAD OBSTETRICIA (filtro del visual).

## Visuales
- **Tarjetas**: TRIAGES ATENDIDOS, TRIAGES GINECO, CONSULTAS URGENCIAS, CONSULTAS PRIORITARIAS, PACIENTES OBSERVADOS y PACIENTES HOSPITALIZADOS.
- **Casillas de edad**: MAYORES DE EDAD y MENORES DE EDAD (columna MENORES).
- **Tabla TRAMO HORARIO**: Triages por hora del día (de 12:00 a. m. a 11:00 p. m.) con total y escala de color de verde (pocos) a rojo (muchos).
- **Tabla CONSULTAS PRIORITARIAS**: DOCUMENTO, PACIENTE, ASEGURADORA, ESTADO CONSULTA y FECHA.
- **CONSULTAS PRIORITARIAS por ESTADO**: Gráfico con la cantidad de consultas prioritarias en cada estado.

## Reglas de negocio
- **Periodo**: Triages con fecha igual a ayer (GETDATE() - 1).
- **Códigos excluidos**: Se excluye el código de triage UA.
- **Agrupación de triage (DESCRI_TRIGE)**: IIIU cuenta como III; IIP e IIS cuentan como II; M es MUERTO; I-G es EMERGENCIA OBSTETRICA, II-G URGENCIA MEDICA OBSTETRICA, III-G URGENCIA OBSTETRICA, IV-G NO URGENTE OBSTETRICA y V-G CONSULTA EXTERNA OBSTETRICA.
- **Agrupación de aseguradora**: Nombres con NUEVA se agrupan como NUEVA EPS; con SURA (salvo Seguros de Vida Sura y Suramericana) como SURA; con SANITAS (salvo Colsanitas y Medisanitas) como SANITAS; con MALLAMAS como MALLAMAS.
- **Grupo de edad**: Menores de 18 años son MENORES DE EDAD; el resto MAYORES DE EDAD.
- **Tramo horario**: La hora del triage se redondea hacia abajo a la hora en punto.
- **Triages en INICIO**: El anillo de INICIO excluye las clasificaciones obstétricas y MUERTO.

## Observaciones
- **Escala de color**: La tabla de tramo horario usa un degradado verde, amarillo y rojo sobre el mínimo, el centro y el máximo de los valores visibles; no hay cortes fijos.
- **Versión de marzo**: La versión de marzo de 2026 tenía un selector de rango (Año, Mes, Semestre o Ayer) y excluía los triages obstétricos en los rangos distintos de AYER; la versión vigente solo muestra el día anterior.
- **Nombre de página**: La página se llama URGENCIAS en Power BI; está oculta y se llega con el botón DETALLE URGENCIAS de INICIO.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
- **2026-11-03 · v3**: Se completó con el PBIP (consultas SQL de las particiones TMDL, campos, agregaciones y filtros de los visuales, relaciones): cálculo de las tarjetas, consultas de origen y escala de color. Autor: agente dic-pendientes.
