---
tablero: TABLERO EPS
pagina: GENERAL
nombre_funcional: Consolidado de atenciones de urgencias por aseguradora
bloque: General
tablas: [OPORTUNIDAD_TRIAGE, ADMISIONES_TRIAGE, ATENCIONES_DIA, CONSULTA_URGENCIAS, CONSULTAS_PRIORITARIAS, PACIENTES_OBSERVADOS, PACIENTES_HOSPITALIZADOS, ATENCIONES_GINECO, %OCUPACIONAL, ASEGURADORAS, GENTERCER, PACIENTES, Calendario]
actualizado: 2026-10-28
version: 2
---

# GENERAL

## Propósito
Tablero «Consolidado de atenciones de urgencias»: muestra el volumen de triages, consultas de urgencias, consultas prioritarias, observación, hospitalización y ocupación de urgencias, filtrable por aseguradora (EPS). Desde la página principal TRIAGES ATENDIDOS se llega a %ATENCIONES/ADMISIONES (con sus páginas de dispersión), al mapa de calor de triages y al detalle de consultas prioritarias. La documentación del propietario se titula «Triages Atendidos».

## Fuentes de datos
- **OPORTUNIDAD_TRIAGE**: Triages de DIM_TRIAGE desde el 2022-01-01 hasta hoy con clasificación, fechas de llegada y de triage, tramo horario, día de la semana, aseguradora y grupo de edad; excluye la clasificación UA.
- **ATENCIONES_DIA**: Por cada hora de hoy cuenta los triages realizados (HCNTRIAGE) y las llegadas registradas en ADMISIONTRIAGE, y calcula los pendientes.
- **ADMISIONES_TRIAGE**: Todos los registros de ADMISIONTRIAGE (llegadas de pacientes a urgencias) desde el 2022-01-01 hasta hoy.
- **CONSULTAS_PRIORITARIAS**: Citas médicas cuya actividad contiene «PRIORITARIA», desde el 2022-01-01 hasta hoy, con estado, aseguradora y grupo de edad.
- **CONSULTA_URGENCIAS**: Triages con su ingreso y primer folio, sin la clasificación UA y sin ingresos con estado 2; fuente de la tarjeta Consultas urgencias.
- **PACIENTES_OBSERVADOS y PACIENTES_HOSPITALIZADOS**: Ingresos desde 2022-01-01 en las áreas de servicio 2 y 42, tipo de ingreso 1 y 2 respectivamente.
- **%OCUPACIONAL**: Ocupación diaria de camas desde 2023-01-01 hasta ayer, con las camas ocupadas y disponibles por servicio.
- **ATENCIONES_GINECO**: Ingresos con causa de ingreso 9 desde 2022-01-01; no alimenta ninguna tarjeta.
- **ASEGURADORAS, GENTERCER y PACIENTES**: Catálogos de apoyo para filtrar por aseguradora y por paciente.

## Definiciones
- **Triage atendido**: Registro de clasificación de triage hecho al paciente en urgencias (tabla DIM_TRIAGE o HCNTRIAGE).
- **Llegada**: Registro de entrada del paciente a urgencias en ADMISIONTRIAGE (HoraEntrada), antes del triage.
- **Tramo horario**: Hora en punto en que ocurre el evento; los minutos se truncan (por ejemplo, 08:45 a. m. queda en 08:00 a. m.).
- **Tiempo de llegada a triage**: Minutos entre el turno de llegada (HCCFECTUR) y la hora del triage (HCTFECTRI); columna MIN.
- **Consulta prioritaria**: Cita de consulta prioritaria de urgencias; en el tablero se asocia a los triages 4 y 5.
- **Consulta de urgencias**: Consulta médica de urgencias; en el tablero se asocia a los triages 1, 2 y 3.
- **Grupo de edad**: «MENORES DE EDAD» si el paciente tiene menos de 18 años; si no, «MAYORES DE EDAD».

## Reglas de negocio
- **Agrupación de aseguradoras**: Nombres que contienen NUEVA quedan como NUEVA EPS; SURA (sin Seguros de Vida Sura ni Suramericana) como SURA; SANITAS (sin Colsanitas ni Medisanitas) como SANITAS; MALLAMAS como MALLAMAS; las demás conservan su nombre.
- **Clasificaciones obstétricas**: Los códigos con sufijo -G se describen como triage obstétrico: I-G emergencia obstétrica, II-G urgencia médica obstétrica, III-G urgencia obstétrica, IV-G no urgente obstétrica y V-G consulta externa obstétrica.
- **Homologación de códigos de triage**: IIIU se describe como III; IIP e IIS como II; M como MUERTO.
- **Exclusión de triage UA**: La clasificación UA no entra en ninguna consulta de triages.
- **Día de la semana**: Se nombra con número de orden: 1. LUNES a 7. DOMINGO, para que las matrices queden ordenadas.
- **Filtros comunes**: Todas las páginas filtran por año, mes, día y aseguradora.

## Observaciones
- **Fuentes de las tarjetas**: Las tarjetas se calculan con agregaciones implícitas en el visual (COUNT y DISTINCTCOUNT); las únicas medidas del modelo son [%ATENCIONES], [%ATENDIDOS] y [%OCUPACIONALC]. Ver el diccionario.
- **Nombre del tablero**: El informe se llama TABLERO EPS; su página principal se llama TRIAGES ATENDIDOS y en pantalla se titula «CONSOLIDADO DE ATENCIONES DE URGENCIAS».

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
