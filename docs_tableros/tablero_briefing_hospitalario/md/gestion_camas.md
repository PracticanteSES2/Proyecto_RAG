---
tablero: BRIEFING HOSPITALARIO
pagina: GESTIÓN CAMAS
nombre_funcional: Capacidad y ocupación de camas por servicio en tiempo real
bloque: Día
tablas: [CAMAS DISPONIBLES, ORDEN CAMAS, SERVICIOS, REPS]
actualizado: 2026-10-28
version: 2
---

# GESTIÓN CAMAS

## Propósito
Muestra el estado actual de la capacidad hospitalaria: total de camas, ocupadas, disponibles, en transición, porcentaje de ocupación y capacidad instalada REPS, con el listado de camas por servicio coloreado por estado. Apoya la asignación de camas y la detección de cuellos de botella. Se llega desde el botón DETALLE GESTIÓN CAMAS del visual %OCUPACIÓN POR SERVICIO en INICIO.

## Fuentes de datos
- **CAMAS DISPONIBLES**: Una fila por cama con código (HCACODIGO), servicio, estado y orden de presentación. Consulta SELECT * FROM CAMAS_DISPONIBLES en el modelo (la documentación original dice CAMAS_DISPONIBLES3); muestra el estado en el momento de la actualización.
- **REPS**: Capacidad instalada habilitada; alimenta la tarjeta CAPACIDAD INSTALADA REPS.

## Indicadores
- **Total camas**: Camas distintas (DISTINCTCOUNT de HCACODIGO) sin EXP ni OH en el código. Los demás criterios de capacidad válida (MOSTRAR distinto de NO MOSTRAR, MOSTRAR_6TO distinto de 0, sin 321 ni 322, sin el servicio CUIDADO ESPECIAL y sin los servicios bloqueados) llegan por los filtros de página; equivale a la medida CamasFiltradas.
- **Camas ocupadas**: Camas distintas con ESTADOS_CAM igual a OCUPADA o CAMA SOLICITADA (estados 2 y 100). La tarjeta no excluye EXP ni OH. Columna OCUPADAS = IF(ESTADO = 2 || ESTADO = 100, 1, 0).
- **Camas disponibles**: Camas distintas con ESTADOS_CAM igual a DISPONIBLE (estado 1), sin EXP ni OH en el código.
- **En transición**: Camas distintas con ESTADOS_CAM igual a EN TRANSICIÓN (estado 5); muestra «(En blanco)» cuando no hay ninguna.
- **%OCUPACION**: Porcentaje de camas ocupadas sobre camas filtradas. DIVIDE(SUM('CAMAS DISPONIBLES'[OCUPADAS]), CamasFiltradas).
- **Capacidad instalada REPS**: Capacidad habilitada según REPS para los grupos de camas del área seleccionada. Cálculo por confirmar.

## Visuales
- **Tarjetas de capacidad**: TOTAL CAMAS, CAMAS OCUPADAS, CAMAS DISPONIBLES, EN TRANSICION, %OCUPACION y CAPACIDAD INSTALADA REPS.
- **Segmentador SERVICIO**: Lista desplegable para filtrar por servicio.
- **Botones por área**: GENERAL, CAMAS HOSPI, CAMAS URGENCIAS, CAMAS GINECO, CAMAS NEONATOS, CUIDADO INTENSIVO, EXPANSION, CAMAS AT DOMICILIARIA y CAMAS_ACV; cada uno aplica un marcador con los servicios o las camas del área.
- **Tabla de camas**: Columnas SERVICIO y CAMA; el color de la celda de la cama indica su estado (ocupada, disponible, solicitada).
- **Camas por servicio**: Anillo con el número y porcentaje de camas de cada servicio sobre el total.
- **Estados de cama**: Anillo ESTADOS con cantidad y porcentaje de camas OCUPADA, DISPONIBLE y CAMA SOLICITADA.

## Reglas de negocio
- **Columna MOSTRAR**: Las camas con EXP en el código se muestran solo si están ocupadas (HCAESTADO = 2); las demás camas se muestran siempre.
- **Estados de cama**: 1 DISPONIBLE, 2 OCUPADA, 3 BLOQUEADA, 5 EN TRANSICIÓN y 100 CAMA SOLICITADA (columna ESTADOS_CAM).
- **Cama solicitada como ocupada**: Una cama en estado 100 (cama solicitada) cuenta como ocupada en OCUPADAS y en %OCUPACION.
- **Exclusiones de capacidad**: El denominador excluye camas de expansión (EXP), camas OH, camas NO MOSTRAR, camas con MOSTRAR_6TO = 0 (sexto piso no habilitado) y las camas administrativas 321 y 322.

## Observaciones
- **Numerador de ocupación sin exclusiones**: SUM(OCUPADAS) no aplica las exclusiones EXP y OH del denominador; una cama de expansión ocupada suma arriba y no abajo, lo que puede subir el porcentaje. Por confirmar si es intencional.
- **Ocupadas que no cuadran**: La tarjeta CAMAS OCUPADAS no excluye camas EXP ni OH y el anillo ESTADOS sí; por eso, en la captura, 235 ocupadas de la tarjeta frente a 233 (OCUPADA más CAMA SOLICITADA) del anillo es esperable cuando hay camas de expansión u OH ocupadas.
- **Marcador CAMAS_ACV**: El botón CAMAS_ACV aplica el marcador de las camas de la ruta ACV (columna RUTA_ACV, 12 códigos de cama fijos). La documentación original no lo describe; su significado clínico está por confirmar.
- **Columna MOSTRAR_6TO**: Viene de la vista CAMAS_DISPONIBLES; el modelo la usa como filtro (distinto de 0) y su regla de origen no está documentada. Por confirmar.
- **Nombre de página**: La página se llama GESTIÓN CAMAS en Power BI; el botón de INICIO dice DETALLE GESTIÓN CAMAS.
- **Página homónima**: Existe otra página GESTIÓN DE CAMAS (flujo de aseo y alistamiento de camas), distinta de esta.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
