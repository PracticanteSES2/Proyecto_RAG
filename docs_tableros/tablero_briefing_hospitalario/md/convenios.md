---
tablero: BRIEFING HOSPITALARIO
pagina: CONVENIOS
nombre_funcional: Convenios del hospital por tipo, vigencia y fecha de finalización
bloque: Día
tablas: [CONVENIOS]
actualizado: 2026-10-20
version: 1
---

# CONVENIOS

## Propósito
Muestra los convenios en trámite u obtenidos por el hospital con cada entidad: tipo, observación, fechas de inicio y fin, tiempo restante y si están vigentes o vencidos. Sirve para anticipar vencimientos y conocer la mezcla de convenios. Se llega desde el botón DETALLE del visual CONVENIOS por TIPO en INICIO.

## Fuentes de datos
- **CONVENIOS**: Archivo Excel «TABLERO CONVENIOS 2026.xlsx» en SharePoint con NIT, entidad, tipo, observación, fecha inicio y fecha final de cada convenio.

## Indicadores
- **Convenios**: Número de convenios. Conteo de filas de CONVENIOS; cálculo exacto por confirmar.
- **Tiempo restante**: Meses y días que faltan para la FECHA FINAL, contando meses de 30 días. Columna RESTANTE.

## Visuales
- **Botones de tipo**: (En blanco), CARTA DE MANIFESTACIÓN DE INTERÉS, CONTRATO, OFERTA PAS, OFERTA PCG y SOAT; filtran la tabla por tipo.
- **Botones de vigencia**: VENCIDO y VIGENTE.
- **Tabla de convenios**: NIT, ENTIDAD, TIPO, OBSERVACION, FECHA INICIO, FECHA FINAL y VIGENCIA (texto de RESTANTE).
- **Segmentadores de finalización**: AÑO, MES y DÍA DE FINALIZACIÓN.
- **CONVENIOS por TIPO**: Anillo con número y porcentaje de convenios por tipo.
- **CANTIDAD DE CONTRATOS POR VIGENCIA**: Anillo con número y porcentaje de convenios vigentes y vencidos.

## Reglas de negocio
- **Columna RESTANTE**: Si la FECHA FINAL ya pasó muestra «CONTRATO VENCIDO»; si faltan 30 días o más muestra «N MESES Y D DÍAS»; si faltan menos de 30 días muestra solo los días.

## Observaciones
- **RESTANTE es columna**: La documentación la presenta como medida, pero usa el valor de cada fila (FECHA FINAL), así que es una columna calculada.
- **Criterio de vigencia**: Cómo se calcula VIGENTE o VENCIDO no está documentado. Por confirmar si compara FECHA FINAL con hoy.
- **Tipo vacío**: Hay convenios sin tipo que aparecen como (En blanco).
- **Siglas PAS y PCG**: Su significado está por confirmar.
- **Nombre de página**: La página no está en la copia local del PBIP. Nombre de página en Power BI por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
