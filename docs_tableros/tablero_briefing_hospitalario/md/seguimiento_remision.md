---
tablero: BRIEFING HOSPITALARIO
pagina: SEGUIMIENTO REMISION
nombre_funcional: Copia oculta de SEGUIMIENTO REMISIONES sin botón de acceso desde INICIO
bloque: Día
tablas: [SEGUIMIENTO REMISIONES]
actualizado: 2026-10-28
version: 1
---

# SEGUIMIENTO REMISION

## Propósito
Copia de la página SEGUIMIENTO REMISIONES con los mismos visuales y los mismos filtros de página. Está oculta y ningún botón de INICIO lleva a ella: el botón SEGUIMIENTO REMISIÓN de INICIO va a SEGUIMIENTO REMISIONES. Solo tiene el botón de casa para volver a INICIO.

## Fuentes de datos
- **SEGUIMIENTO REMISIONES**: Vista Con_SeguimientoRemisiones de PLANILLAUSUARIO con las remisiones en trámite; ver la página SEGUIMIENTO REMISIONES.

## Indicadores
- **Total remisiones**: Número de ingresos con remisión en trámite. DISTINCTCOUNT(SEGUIMIENTO REMISIONES[Ingreso]).

## Visuales
- **Botón de inicio**: Icono de casa que regresa a INICIO.
- **Tarjeta TOTAL REMISIONES**: Total según los filtros aplicados.
- **Segmentadores**: EPS (SEGUIMIENTO REMISIONES[EPS]) y SERVICIO (SEGUIMIENTO REMISIONES[SERVICIO]).
- **Tabla INGRESO**: INGRESO, REMISION, CEDULA, PACIENTE, EPS, ESPECIALIDAD, MOTIVO REMISIÓN, FECHA REMISION, SERVICIO y ESTADO TRAMITE.
- **Anillo EPS**: Número y porcentaje de remisiones por EPS.
- **Anillo SERVICIO**: Número y porcentaje de remisiones por servicio que remite.

## Reglas de negocio
- **Filtros de página**: Los mismos de SEGUIMIENTO REMISIONES: excluye servicios vacíos, ATENCION DOMICILIARIA, los BLOQUEAR, CAMAS MAL CREADAS EN EL SISTEMA, HOSPITALIZACION PARCIAL, IMAGENES, QUIROFANO y UNIDAD NEUROCARDIOVASCULAR, y camas EXP, 321, 322, NO MOSTRAR o con MOSTRAR_6TO = 0.

## Observaciones
- **Página duplicada**: Por confirmar si la copia es un residuo y puede eliminarse.

## Historial de cambios
- **2026-10-28 · v1**: Página creada a partir del informe: copia oculta de SEGUIMIENTO REMISIONES.
