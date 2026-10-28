---
tablero: BRIEFING HOSPITALARIO
pagina: GENERAL
nombre_funcional: Briefing diario de ocupación, camas, flujo de pacientes y pendientes institucionales
bloque: General
tablas: [CAMAS DISPONIBLES, SOLICITUD CAMAS, PACIENTES X ASEGURADORA, EGRESOS PROBABLES, INGRESOS, EGRESOS, SEGUIMIENTO REMISIONES, DETALLE RECEPCION, NEDOCS, TRIAGES, INTERCONSULTAS, BOLETIN, MEDICAMENTOS DESABASTECIDOS, REPS, CONVENIOS, ATENCIONES_SERVICIO, IMAGENES_TOMADAS, AMBULATORIO_SS, GESTIÓN CAMAS]
actualizado: 2026-10-28
version: 2
---

# GENERAL

## Propósito
Tablero de consulta diaria de la gerencia y las coordinaciones asistenciales. Reúne en la página INICIO los indicadores de ocupación de camas, solicitudes de cama, remisiones, recepciones, egresos probables, ingresos y egresos, urgencias (NEDOCS y triage) y pendientes institucionales (interconsultas, medicamentos desabastecidos, casos del briefing, convenios). Cada visual de INICIO tiene un botón DETALLE que lleva a una página oculta con el listado; todas las páginas de detalle tienen un botón con una casa para volver a INICIO.

## Fuentes de datos
- **Dinámica Gerencial (DGEMPRES10)**: Base del sistema de información hospitalario; aporta ingresos, camas, estancias, pacientes, folios, interconsultas y aseguradoras.
- **PLANILLAUSUARIO**: Base de aplicativos internos; aporta remisiones, solicitudes de servicio (briefing y desabastecidos), NEDOCS, egresos y programación de cirugía.
- **Bodega de datos (DW)**: Tablas DIM_ y FACT_ (por ejemplo FACT_SOLICITUD_CAMA, FACT_EGRESOS_PROBABLES, DIM_TRIAGE, DIM_INGRESO) usadas por varias consultas.
- **Archivos Excel en SharePoint**: Capacidad instalada REPS, convenios y pacientes del movimiento telúrico se cargan desde archivos Excel.
- **Modo de carga**: Las tablas del modelo están en modo importación; la frecuencia de actualización programada está por confirmar.

## Definiciones
- **Servicio**: Unidad o piso de hospitalización donde está la cama (HPNSUBGRU, columna HSUNOMBRE), por ejemplo URGENCIAS, CUARTO PISO SUR o UNIDAD DE CUIDADO INTENSIVO.
- **Estado de cama**: Código CAMAS DISPONIBLES[ESTADO] traducido en ESTADOS_CAM: 1 DISPONIBLE, 2 OCUPADA, 3 BLOQUEADA, 5 EN TRANSICIÓN y 100 CAMA SOLICITADA.
- **Cama ocupada**: Cama en estado 2 (ocupada) o 100 (cama solicitada); columna CAMAS DISPONIBLES[OCUPADAS] vale 1 en esos casos.
- **Cama de expansión (EXP)**: Cama cuyo código contiene EXP; solo se muestra cuando está ocupada y no cuenta en el denominador de ocupación.
- **Camas filtradas**: Capacidad válida del hospital: camas sin EXP ni OH en el código, marcadas MOSTRAR, con MOSTRAR_6TO distinto de 0 y distintas de las camas administrativas 321 y 322.
- **Porcentaje de ocupación**: Camas ocupadas sobre camas filtradas (medida %OCUPACION).
- **Solicitud de cama pendiente**: Solicitud en estado 2 o 3 que todavía no tiene cama asignada.
- **Remisión**: Traslado de un paciente del hospital hacia otra institución, en trámite.
- **Pendiente de recepción**: Paciente que otra entidad pide remitir al hospital y que aún no ha sido recibido.
- **Egreso probable**: Paciente hospitalizado con fecha estimada de salida registrada.
- **Egreso efectivo hoy**: Paciente con epicrisis u orden de salida registrada en la fecha de hoy.
- **Días de estancia**: Días calendario entre la fecha de ingreso (AINFECING) y hoy.
- **NEDOCS**: Escala de sobreocupación del servicio de urgencias calculada con siete variables (ver DETALLE NEDOCS).
- **Triage**: Clasificación de prioridad de urgencias de I (más urgente) a V; las variantes obstétricas terminan en -G.
- **Caso del briefing**: Solicitud interna registrada por un área para el briefing diario (categoría 366 de solicitudes de servicio).
- **REPS**: Registro Especial de Prestadores de Servicios de Salud; capacidad instalada habilitada (camas, camillas, consultorios, salas y sillas).

## Reglas de negocio
- **Navegación**: Solo INICIO es visible; las demás páginas están ocultas y se abren con los botones DETALLE de INICIO o con botones entre páginas.
- **Servicios bloqueados**: Los listados de servicio excluyen los nombres que empiezan por BLOQUEAR y CAMAS MAL CREADAS EN EL SISTEMA.
- **Camas administrativas**: Las camas cuyo código contiene 321 o 322 se excluyen de los indicadores de camas.
- **Ingresos anulados**: Las consultas de ingresos excluyen los ingresos anulados (AINESTADO = 2).

## Observaciones
- **PBIP actualizado**: El PBIP local tiene las 21 páginas y los visuales de INICIO; cuando la documentación original difiere del informe se documenta el informe. La página OCUPACIÓN POR ESTANCIA y la tabla PACIENTES POR ESTANCIA ya no existen en el informe.
- **Página duplicada**: SEGUIMIENTO REMISION es una copia oculta de SEGUIMIENTO REMISIONES sin acceso desde INICIO.
- **Versiones de la documentación**: Existen versiones de marzo de 2026 (carpeta Documentacion) y de septiembre de 2026 (data/raw). Se usó la de septiembre como vigente y se anotan en cada página las diferencias relevantes.
- **Sentido de remisión y recepción**: Se interpreta remisión como salida de pacientes del hospital y recepción como llegada desde otra entidad, según las columnas de cada fuente (servicio del hospital y entidad que remite). Por confirmar.
- **Sigla OH**: Las camas con OH en el código se excluyen de la ocupación; el significado de OH está por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
