---
tablero: BRIEFING HOSPITALARIO
pagina: SEGUIMIENTO REMISIONES
nombre_funcional: Remisiones de pacientes a otras instituciones en trámite
bloque: Día
tablas: [SEGUIMIENTO REMISIONES]
actualizado: 2026-10-28
version: 2
---

# SEGUIMIENTO REMISIONES

## Propósito
Seguimiento de las remisiones de pacientes del hospital que están en trámite: total de remisiones, detalle por paciente y distribución por EPS y por servicio. Sirve para gestionar los traslados pendientes y su trazabilidad. Se llega desde el botón SEGUIMIENTO REMISIÓN del visual REMISIONES por SERVICIO en INICIO.

## Fuentes de datos
- **SEGUIMIENTO REMISIONES**: Vista Con_SeguimientoRemisiones de PLANILLAUSUARIO con ingreso, número de remisión, cédula, paciente, EPS, servicio del hospital, fecha de trámite, estado del trámite, especialidad (GEEDESCRI) y motivo de remisión. Trae ingresos de los últimos 200 días.

## Indicadores
- **Total remisiones**: Número de ingresos con remisión en trámite. DISTINCTCOUNT(SEGUIMIENTO REMISIONES[Ingreso]).

## Visuales
- **Tarjeta TOTAL REMISIONES**: Total según los filtros aplicados.
- **Segmentadores**: EPS y SERVICIO.
- **Tabla de remisiones**: INGRESO, REMISION, CEDULA, PACIENTE, EPS, ESPECIALIDAD, MOTIVO REMISIÓN, FECHA REMISION, SERVICIO y ESTADO TRAMITE.
- **Remisiones por EPS**: Anillo con número y porcentaje de remisiones por EPS.
- **Remisiones por servicio**: Anillo con número y porcentaje de remisiones por servicio que remite.

## Reglas de negocio
- **Periodo**: Ingresos con FechaIngreso entre hoy menos 200 días y hoy.
- **Estado de la remisión**: Solo registros con EstadoOid = 1 y EstadosRecOid = 4.
- **Servicios excluidos**: Filtro de página que excluye servicios vacíos, ATENCION DOMICILIARIA, los BLOQUEAR, CAMAS MAL CREADAS EN EL SISTEMA, HOSPITALIZACION PARCIAL, IMAGENES, QUIROFANO y UNIDAD NEUROCARDIOVASCULAR.
- **Camas excluidas**: Filtros de página que excluyen camas EXP, camas con 321 o 322 en el código, camas NO MOSTRAR y camas con MOSTRAR_6TO = 0.

## Observaciones
- **Significado de estados**: Qué representan EstadoOid = 1 y EstadosRecOid = 4 no está documentado. Por confirmar.
- **Filtros de página heredados**: Los filtros sobre SERVICIOS y CAMAS DISPONIBLES solo afectan esta página si esas tablas están relacionadas con SEGUIMIENTO REMISIONES. Por confirmar.
- **Nombre del botón**: En INICIO el botón dice SEGUIMIENTO REMISIÓN y la página se llama SEGUIMIENTO REMISIONES.
- **Página duplicada**: El informe tiene una copia oculta llamada SEGUIMIENTO REMISION con los mismos visuales; ver su página.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
