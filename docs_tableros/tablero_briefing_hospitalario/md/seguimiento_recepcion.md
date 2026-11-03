---
tablero: BRIEFING HOSPITALARIO
pagina: SEGUIMIENTO RECEPCIÓN
nombre_funcional: Pacientes remitidos por otras entidades pendientes de recepción
bloque: Día
tablas: [DETALLE RECEPCION]
actualizado: 2026-11-03
version: 3
---

# SEGUIMIENTO RECEPCIÓN

## Propósito
Seguimiento de los pacientes que otras entidades solicitan remitir al hospital y que aún no han sido recibidos: total de pendientes, detalle por paciente y distribución por EPS y por servicio. Sirve para gestionar a tiempo la aceptación y el ingreso de estos pacientes. Se llega desde el botón SEGUIMIENTO RECEPCIÓN del visual PENDIENTES RECEPCIÓN por SERVICIO en INICIO.

## Fuentes de datos
- **DETALLE RECEPCION**: Solicitudes de recepción pendientes con documento, nombre, edad, fecha de la llamada, entidad que remite (PRESTADOR), EPS (nombreps), diagnóstico inicial, servicio y observaciones. Consulta: SELECT * FROM PLANILLAUSUARIO.DBO.Rec_SeguimientoRecepciones con OidEstado = 7.

## Indicadores
- **Pendientes recepción**: Número de solicitudes pendientes de recepción. DISTINCTCOUNT(DETALLE RECEPCION[Oid]).

## Visuales
- **Tarjeta PENDIENTES RECEPCIÓN**: Total según los filtros aplicados.
- **Segmentadores**: EPS (DETALLE RECEPCION[nombreps]) y SERVICIO (DETALLE RECEPCION[SERVICIO], campo SERVICIO1).
- **Tabla de pendientes**: DOCUMENTO, PACIENTE, EDAD, LLAMADA (fecha de la llamada), ENTIDAD QUE REMITE, EPS, DIAGNOSTICO, SERVICIO y OBSERVACIONES.
- **Pendientes por EPS**: Anillo con número y porcentaje de pendientes por EPS.
- **Pendientes por servicio**: Anillo con número y porcentaje de pendientes por servicio solicitado.

## Reglas de negocio
- **Entidad propia excluida**: Filtro de página que excluye las solicitudes cuyo PRESTADOR es SERVICIOS ESPECIALES DE SALUD.
- **Servicios y camas excluidos**: La página repite los filtros de SEGUIMIENTO REMISIONES sobre servicios (BLOQUEAR, ATENCION DOMICILIARIA, HOSPITALIZACION PARCIAL, IMAGENES, QUIROFANO, UNIDAD NEUROCARDIOVASCULAR, CAMAS MAL CREADAS EN EL SISTEMA) y sobre camas (EXP, 321, 322, NO MOSTRAR, MOSTRAR_6TO = 0).

## Observaciones
- **Consulta equivocada en la documentación**: La documentación original copia la consulta de remisiones (Con_SeguimientoRemisiones); la consulta real de DETALLE RECEPCION es SELECT * FROM PLANILLAUSUARIO.DBO.Rec_SeguimientoRecepciones WHERE OidEstado IN (7).
- **Criterio de pendiente**: Un caso cuenta como pendiente de recepción si su OidEstado es 7 (filtro de la consulta); el nombre de ese estado está por confirmar.
- **Filtros de página heredados**: Los filtros de página sobre SERVICIOS y CAMAS DISPONIBLES no afectan esta página: DETALLE RECEPCION no tiene relaciones en el modelo.
- **Título con error**: La tarjeta del PBIP dice «PENDIENTES RECECPCIÓN».

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
- **2026-11-03 · v3**: Se completó con el PBIP (consultas SQL de las particiones TMDL, campos, agregaciones y filtros de los visuales, relaciones): consulta de DETALLE RECEPCION, criterio de pendiente y relaciones. Autor: agente dic-pendientes.
