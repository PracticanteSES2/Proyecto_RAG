---
tablero: BRIEFING HOSPITALARIO
pagina: URGENCIAS
nombre_funcional: Comportamiento del servicio de urgencias del día anterior
bloque: Día
tablas: [TRIAGES]
actualizado: 2026-10-28
version: 2
---

# URGENCIAS

## Propósito
Resume la actividad del servicio de urgencias del día anterior: triages atendidos (generales y gineco), consultas de urgencias, consultas prioritarias, pacientes en observación y hospitalizados, con los triages por hora y el detalle de consultas prioritarias. Sirve para identificar picos de demanda y organizar el personal. Se llega desde el botón DETALLE URGENCIAS del visual TRIAGES por CLASIFICACIÓN en INICIO.

## Fuentes de datos
- **TRIAGES**: Triages del día anterior (DIM_TRIAGE) con clasificación, aseguradora, fecha y hora del triage, hora de llegada a portería, tramo horario, día de la semana y grupo de edad.
- **Otras tablas**: Las fuentes de consultas de urgencias, consultas prioritarias, pacientes observados y hospitalizados no están documentadas. Por confirmar.

## Indicadores
- **Triages atendidos**: Número de triages del día anterior. Conteo de OID_TRIAGE; cálculo exacto por confirmar.
- **Triages gineco**: Triages con clasificación obstétrica (códigos terminados en -G). Cálculo por confirmar.
- **Consultas urgencias**: Consultas médicas de urgencias. Cálculo por confirmar.
- **Consultas prioritarias**: Consultas por el canal de consulta prioritaria; muestra «(En blanco)» si no hay. Cálculo por confirmar.
- **Pacientes observados**: Pacientes en observación de urgencias. Cálculo por confirmar.
- **Pacientes hospitalizados**: Pacientes de urgencias hospitalizados. Cálculo por confirmar.

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
- **Escala de color**: La tabla de tramo horario usa una escala de color sin umbrales documentados. Por confirmar si hay cortes fijos.
- **Versión de marzo**: La versión de marzo de 2026 tenía un selector de rango (Año, Mes, Semestre o Ayer) y excluía los triages obstétricos en los rangos distintos de AYER; la versión vigente solo muestra el día anterior.
- **Nombre de página**: La página se llama URGENCIAS en Power BI; está oculta y se llega con el botón DETALLE URGENCIAS de INICIO.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
