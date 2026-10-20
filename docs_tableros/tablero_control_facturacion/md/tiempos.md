---
tablero: TABLERO CONTROL FACTURACION
pagina: TIEMPOS
nombre_funcional: Tiempos entre etapas del proceso de facturación
bloque: Histórico
tablas: [FACTURACION, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# TIEMPOS

## Propósito
Analiza los tiempos entre las etapas del proceso de facturación: del egreso a la prefactura, del facturador a auditoría de pertinencia, de pertinencia a auditoría de medicamentos y de medicamentos de vuelta al facturador, y la evolución mensual de las dos auditorías. Análisis histórico por año y mes, separado en ambulatorio y hospitalario; se llega desde el botón TIEMPOS de PROCESO FACTURACION.

## Fuentes de datos
- **FACTURACION**: Una fila por ingreso con la primera fecha de recibe y de entrega de cada perfil en columnas (por ejemplo RECIBE CUENTAS, ENTREGA AUDITORIA PERTINENCIA), la fecha de salida, la asignación y respuesta de las auditorías (REC_AUDITORIA_MED, RESP_AUDITORIA_MED, REC_AUDITORIA_PER, RESP_AUDITORIA_PER), los responsables y el tipo de ingreso. Egresos desde el 1 de agosto de 2025.

## Indicadores
- **Tiempo de auditoría de pertinencia**: Horas entre la asignación y la respuesta de la auditoría de pertinencia. Columna FACTURACION[AUDITORIA_PERTINENCIA] = DATEDIFF(REC_AUDITORIA_PER, RESP_AUDITORIA_PER, HOUR).
- **Tiempo de pertinencia a medicamentos**: Minutos entre la entrega de auditoría de pertinencia y el recibe de auditoría de medicamentos. Columna FACTURACION[TIEMPO_AUDITORIA_MEDICAMENTOS] = DATEDIFF([ENTREGA AUDITORIA PERTINENCIA], [RECIBE AUDITORIA MEDICAMENTOS], MINUTE).
- **Tiempo del egreso a la prefactura**: Promedio de TIEMPO_PREFACTURA. Cálculo y unidad por confirmar.
- **Tiempo del facturador a pertinencia**: Promedio de TIEMPO AUDITORIA PERTINENCIA (nombre visible en el eje). Cálculo y unidad por confirmar.
- **Tiempo de medicamentos al facturador**: Promedio de TIEMPO FACTURADOR. Cálculo y unidad por confirmar.

## Visuales
- **Filtros**: Segmentadores de Año y Mes y botones AMBULATORIO / HOSPITALARIO.
- **Egreso a prefactura**: Gráfico titulado «Tiempo entre el egreso del paciente y la prefactura»; promedio de TIEMPO_PREFACTURA.
- **Facturador a pertinencia**: Gráfico titulado «Tiempo entre la entrega del facturador a auditoria de pertinencia».
- **Pertinencia a medicamentos**: Gráfico titulado «Tiempo recepción y entrega por parte del auditor de pertinencia a auditoria de medicamentos»; promedio de TIEMPO_AUDITORIA_MEDICAMENTOS.
- **Medicamentos a facturador**: Gráfico titulado «Tiempo recepción y entrega por parte de auditoria medicamentos a facturador»; promedio de TIEMPO FACTURADOR.
- **Línea auditoría medicamentos**: Titulada «AUDITORÍA MEDICAMENTOS»; promedio mensual del tiempo de auditoría de medicamentos.
- **Línea auditoría de pertinencia**: Titulada «AUDITORIA DE PERTINENCIA»; promedio mensual de AUDITORIA_PERTINENCIA, en horas.

## Reglas de negocio
- **Fechas por etapa**: Para cada ingreso y perfil se toma el primer registro de recibe (el más antiguo) y su entrega.
- **Auditorías**: Asignación (estado 2) y respuesta (estado 4) se toman de las solicitudes de auditoría (servicio categoría 374), la primera de cada estado.

## Observaciones
- **Unidades mezcladas**: TIEMPO_AUDITORIA_MEDICAMENTOS está en minutos y AUDITORIA_PERTINENCIA en horas.
- **Columnas sin documentar**: TIEMPO_PREFACTURA, TIEMPO AUDITORIA PERTINENCIA, TIEMPO FACTURADOR y la columna de la línea de auditoría de medicamentos no tienen fórmula documentada. Por confirmar.
- **Gráficos vacíos**: En la captura de la documentación (filtro HOSPITALARIO) los cuatro gráficos superiores aparecen sin datos.
- **Página más alta**: La página mide 1.280 × 1.000 píxeles (más alta que las demás) y requiere desplazamiento.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
