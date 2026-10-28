---
tablero: TABLERO CONTROL FACTURACION
pagina: TIEMPOS
nombre_funcional: Tiempos entre etapas del proceso de facturación
bloque: Histórico
tablas: [FACTURACION, CALENDARIO]
actualizado: 2026-10-28
version: 2
---

# TIEMPOS

## Propósito
Analiza los tiempos entre las etapas del proceso de facturación: del egreso a la prefactura, del facturador a auditoría de pertinencia, de pertinencia a auditoría de medicamentos y de medicamentos de vuelta al facturador, y la evolución mensual de las dos auditorías. Análisis histórico por año y mes, separado en ambulatorio y hospitalario; se llega desde el botón TIEMPOS de PROCESO FACTURACION.

## Fuentes de datos
- **FACTURACION**: Una fila por ingreso con la primera fecha de recibe y de entrega de cada perfil en columnas (por ejemplo RECIBE CUENTAS, ENTREGA AUDITORIA PERTINENCIA), la fecha de salida, la asignación y respuesta de las auditorías (REC_AUDITORIA_MED, RESP_AUDITORIA_MED, REC_AUDITORIA_PER, RESP_AUDITORIA_PER), los responsables y el tipo de ingreso. Egresos desde el 1 de agosto de 2025.

## Indicadores
- **Tiempo de auditoría de pertinencia**: Horas entre la asignación y la respuesta de la auditoría de pertinencia. Columna FACTURACION[AUDITORIA_PERTINENCIA] = DATEDIFF(REC_AUDITORIA_PER, RESP_AUDITORIA_PER, HOUR).
- **Tiempo de pertinencia a medicamentos**: Minutos entre la entrega de auditoría de pertinencia y el recibe de auditoría de medicamentos. Columna FACTURACION[TIEMPO_AUDITORIA_MEDICAMENTOS] = DATEDIFF([ENTREGA AUDITORIA PERTINENCIA], [RECIBE AUDITORIA MEDICAMENTOS], MINUTE).
- **Tiempo del egreso a la prefactura**: Promedio mensual de FACTURACION[TIEMPO_PREFACTURA], en minutos: de la entrega de ESTACION DE ENFERMERIA a la entrega de FACTURADOR SERVICIO. El título del gráfico habla del egreso del paciente, pero la fecha de egreso no interviene en el cálculo.
- **Tiempo del facturador a pertinencia**: Promedio mensual de FACTURACION[TIEMPO AUDITORIA PERTINENCIA], en minutos: de la entrega de FACTURADOR SERVICIO al recibe de AUDITORIA PERTINENCIA.
- **Tiempo de medicamentos al facturador**: Promedio mensual de FACTURACION[TIEMPO FACTURADOR], en minutos: de la entrega de AUDITORIA MEDICAMENTOS al recibe de FACTURACION (perfil 13)
- **Tiempo de auditoría de medicamentos**: Horas entre la asignación y la respuesta de la auditoría de medicamentos. Columna FACTURACION[AUDITORIA_MEDICAMENTOS] = DATEDIFF(REC_AUDITORIA_MED, RESP_AUDITORIA_MED, HOUR)

## Visuales
- **Filtros**: Segmentadores «FECHA_SALIDA Año» y «FECHA_SALIDA Mes» (jerarquía de fechas de FACTURACION[FECHA_SALIDA], fecha de egreso) y «TIPO_INGRESO» (DIM_TIPO_INGRESO[TIPO_INGRESO], botones AMBULATORIO / HOSPITALARIO); botón de inicio que vuelve a INICIO.
- **Egreso a prefactura**: Gráfico de líneas «Tiempo entre el egreso del paciente y la prefactura»; promedio de TIEMPO_PREFACTURA por año y mes de egreso, en minutos.
- **Facturador a pertinencia**: Gráfico de líneas «Tiempo entre la entrega del facturador a auditoria de pertinencia»; promedio de TIEMPO AUDITORIA PERTINENCIA por año y mes de egreso, en minutos.
- **Pertinencia a medicamentos**: Gráfico titulado «Tiempo recepción y entrega por parte del auditor de pertinencia a auditoria de medicamentos»; promedio de TIEMPO_AUDITORIA_MEDICAMENTOS.
- **Medicamentos a facturador**: Gráfico titulado «Tiempo recepción y entrega por parte de auditoria medicamentos a facturador»; promedio de TIEMPO FACTURADOR.
- **Línea auditoría medicamentos**: Gráfico de líneas «AUDITORÍA MEDICAMENTOS»; promedio de AUDITORIA_MEDICAMENTOS por año y mes de egreso, en horas.
- **Línea auditoría de pertinencia**: Gráfico de líneas «AUDITORIA DE PERTINENCIA»; promedio de AUDITORIA_PERTINENCIA por año y mes de egreso, en horas.

## Reglas de negocio
- **Fechas por etapa**: Para cada ingreso y perfil se toma el primer registro de recibe (el más antiguo) y su entrega.
- **Auditorías**: Asignación (estado 2) y respuesta (estado 4) se toman de las solicitudes de auditoría (servicio categoría 374), la primera de cada estado.

## Observaciones
- **Unidades mezcladas**: TIEMPO_AUDITORIA_MEDICAMENTOS está en minutos y AUDITORIA_PERTINENCIA en horas.
- **Gráficos vacíos**: En la captura de la documentación (filtro HOSPITALARIO) los cuatro gráficos superiores aparecen sin datos.
- **Página más alta**: La página mide 1.280 × 1.000 píxeles (más alta que las demás) y requiere desplazamiento.
- **Columnas sin visual**: FACTURACION[TIEMPO RADICACION], FACTURACION[TIEMPO_MODIFICACION_FACT] y las columnas NOM_COM_* existen en el modelo pero ningún visual del PBIP las usa.
- **Sin botón de entrada**: Ninguna página del PBIP tiene un botón hacia TIEMPOS; la documentación decía que se llegaba desde PROCESO FACTURACION, que no está en el PBIP. Página oculta.
- **Egreso o entrega**: El gráfico «Tiempo entre el egreso del paciente y la prefactura» usa TIEMPO_PREFACTURA, que parte de la entrega de ESTACION DE ENFERMERIA y no del egreso. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
