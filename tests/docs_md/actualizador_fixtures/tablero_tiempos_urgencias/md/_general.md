---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: TABLERO TIEMPOS URGENCIAS
nombre_funcional: Tiempos de Urgencias (descripción general)
bloque: General
tablas: []
actualizado: 2026-10-20
version: 1
---

# TABLERO TIEMPOS URGENCIAS

## Propósito
Mide la oportunidad de la atención en el servicio de urgencias en cada etapa del recorrido del paciente: triage, admisión, consulta, ingreso por enfermería, observación, apoyos diagnósticos, hospitalización y egreso. Tiene un bloque de tiempo real (páginas «DIA») y un bloque histórico por año y mes desde 2023. La página de inicio es RESUMEN_D.

## Fuentes de datos
- **DWSES**: Base de datos SQL Server LS-COBRA,1433\dinamica; única conexión del modelo, todas las tablas se cargan con sentencias SQL nativas.
- **PLANILLAUSUARIO**: Base auxiliar con el digiturno, las solicitudes de hospitalización, las remisiones y el censo de urgencias.

## Definiciones
- **Tiempo para triage**: Minutos entre la toma del turno en el digiturno y el registro del triage.
- **Tiempo para el egreso**: Minutos entre el último folio de historia clínica y la orden de salida. Válido si es mayor que 0 y menor o igual a 720 minutos.
- **Tiempo para hospitalización (día)**: Horas entre la solicitud de hospitalización y la asignación de cama.
- **Semáforo de oportunidad**: Formato condicional de las tablas del día: verde dentro del tiempo esperado, amarillo en alerta y rojo fuera de tiempo.

## Reglas de negocio
- **Exclusión del triage UA**: Todas las consultas que leen triages excluyen el código UA.
- **Unidad de urgencias**: El subgrupo de camas 16 corresponde a URGENCIAS.

## Observaciones
- **Frecuencia de actualización**: La actualización programada del conjunto de datos no está en el PBIP. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
