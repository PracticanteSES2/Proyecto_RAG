---
tablero: BRIEFING HOSPITALARIO
pagina: DETALLE GESTIÓN CAMAS
nombre_funcional: Capacidad y ocupación de camas por servicio en tiempo real
bloque: Día
tablas: [CAMAS DISPONIBLES, ORDEN CAMAS, SERVICIOS, REPS]
actualizado: 2026-10-20
version: 1
---

# DETALLE GESTIÓN CAMAS

## Propósito
Muestra el estado actual de la capacidad hospitalaria: total de camas, ocupadas, disponibles, en transición, porcentaje de ocupación y capacidad instalada REPS, con el listado de camas por servicio coloreado por estado. Apoya la asignación de camas y la detección de cuellos de botella. Se llega desde el botón DETALLE GESTIÓN CAMAS del visual %OCUPACIÓN POR SERVICIO en INICIO.

## Fuentes de datos
- **CAMAS DISPONIBLES**: Una fila por cama con código (HCACODIGO), servicio, estado y orden de presentación. Consulta SELECT * FROM CAMAS_DISPONIBLES3; muestra el estado en el momento de la actualización.
- **REPS**: Capacidad instalada habilitada; alimenta la tarjeta CAPACIDAD INSTALADA REPS.

## Indicadores
- **Total camas**: Camas de la capacidad válida. Medida CamasFiltradas: DISTINCTCOUNT de HCACODIGO sin EXP ni OH, MOSTRAR = "MOSTRAR", MOSTRAR_6TO <> 0 y código distinto de 321 y 322.
- **Camas ocupadas**: Camas en estado 2 u 100. Columna OCUPADAS = IF(ESTADO = 2 || ESTADO = 100, 1, 0).
- **Camas disponibles**: Camas en estado 1 (DISPONIBLE). Cálculo exacto de la tarjeta por confirmar.
- **En transición**: Camas en estado 5 (EN TRANSICIÓN); muestra «(En blanco)» cuando no hay ninguna.
- **%OCUPACION**: Porcentaje de camas ocupadas sobre camas filtradas. DIVIDE(SUM('CAMAS DISPONIBLES'[OCUPADAS]), CamasFiltradas).
- **Capacidad instalada REPS**: Capacidad habilitada según REPS para los grupos de camas del área seleccionada. Cálculo por confirmar.

## Visuales
- **Tarjetas de capacidad**: TOTAL CAMAS, CAMAS OCUPADAS, CAMAS DISPONIBLES, EN TRANSICION, %OCUPACION y CAPACIDAD INSTALADA REPS.
- **Segmentador SERVICIO**: Lista desplegable para filtrar por servicio.
- **Botones por área**: GENERAL, HOSPITALIZACIÓN, URGENCIAS, GINECOBSTETRICIA, NEONATOS, CUIDADO CRÍTICO, EXPANSIÓN y SES EN TU HOGAR; cada uno aplica un marcador con los servicios del área.
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
- **Ocupadas que no cuadran**: En la captura, la tarjeta CAMAS OCUPADAS (235) no coincide con OCUPADA más CAMA SOLICITADA del gráfico de estados (233). Por confirmar si usan filtros distintos.
- **Marcador CAMAS_ACV**: El PBIP tiene un marcador CAMAS_ACV (camas de la ruta ACV, columna RUTA_ACV) que no aparece en la documentación. Por confirmar si hay botón visible.
- **Columna MOSTRAR_6TO**: Su origen y regla no están documentados. Por confirmar.
- **Nombre de página**: La página del PBIP no tiene nombre visible en la copia local; se usa el texto del botón de INICIO. Nombre de página en Power BI por confirmar.
- **Página homónima**: Existe otra página GESTIÓN DE CAMAS (flujo de aseo y alistamiento de camas), distinta de esta.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
