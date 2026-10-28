---
tablero: TABLERO TIEMPOS URGENCIAS
pagina: ADMISIONES DIA
nombre_funcional: Oportunidad en las admisiones del día
bloque: Día
tablas: [ESPERA_ADMISION, ADMISIONES_DIA]
actualizado: 2026-10-20
version: 1
---

# ADMISIONES DIA

## Propósito
Muestra la oportunidad de la admisión (registro administrativo o de facturación) después del triage: a la izquierda los pacientes con triage que aún no tienen admisión y su espera, y a la derecha los admitidos con hora del triage, hora de admisión y tiempo transcurrido, con semáforo. Se llega desde el botón de admisión de RESUMEN_D y el botón superior izquierdo regresa a RESUMEN_D.

## Fuentes de datos
- **ESPERA_ADMISION**: Triages sin admisión de las clasificaciones que requieren admisión, sin límite de fecha; tabla en DirectQuery.
- **ADMISIONES_DIA**: Triages con admisión cuya fecha de admisión es la del día de la última actualización; tabla en Import.

## Indicadores
- **Tiempo en espera de admisión**: Minutos desde el registro del triage hasta la hora actual, para triages sin admisión. Columna ESPERA_ADMISION[TIEMPO_ESPERA_ADMI].
- **Tiempo entre triage y admisión**: Minutos entre el registro del triage y la admisión. Columna ADMISIONES_DIA[TIEMPO_ESPERA].

## Visuales
- **Leyenda de oportunidad**: Texto con los rangos del semáforo: 0-10 minutos, 11-20 minutos y 21 minutos o más.
- **Tabla en espera admisión**: Columnas DOCUMENTO (registrado en el triage), PACIENTE y TIEMPO EN ESPERA.
- **Tabla pacientes con admisión**: Columnas DOCUMENTO, PACIENTE, HORA TRIAGE, HORA ADMISION y TIEMPO DE ESPERA. Sus filtros sobre TRIAGES_DIA (MIN no vacío y sin URGENCIA OBSTETRICA) no tienen efecto porque esa tabla no se relaciona con ADMISIONES_DIA.

## Reglas de negocio
- **Semáforo de admisión**: En ambas tablas, verde de 0 a 10 minutos, amarillo de 11 a 20 y rojo de 21 o más.
- **Paciente en espera de admisión**: Triage sin ingreso asociado, no confirmado (HCTCONFIR = 0) y con clasificación de identificador interno 2, 7, 9, 16, 17, 18 o 19.
- **Espera sin límite de fecha**: La lista de espera muestra todos los triages pendientes de admisión, sin importar el día.
- **Admisiones del día importadas**: La tabla de pacientes con admisión muestra el día de la última actualización del conjunto de datos, no necesariamente hoy.

## Observaciones
- **ADMISIONES_DIA en Import**: Entre actualizaciones la tabla de admitidos no cambia, mientras que la de espera (DirectQuery) sí. Por confirmar si debe pasarse a DirectQuery.
- **Identificadores de clasificación**: La correspondencia de los identificadores 2, 7, 9, 16, 17, 18 y 19 con los niveles I a V está por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del PBIP y de la documentación versión 2.
