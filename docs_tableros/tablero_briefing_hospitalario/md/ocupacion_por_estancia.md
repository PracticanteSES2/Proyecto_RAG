---
tablero: BRIEFING HOSPITALARIO
pagina: OCUPACIÓN POR ESTANCIA
nombre_funcional: Censo de pacientes hoy frente al censo de hace un mes, un semestre o un año
bloque: Histórico
tablas: [PACIENTES POR ESTANCIA]
actualizado: 2026-10-20
version: 1
---

# OCUPACIÓN POR ESTANCIA

## Propósito
Compara por servicio el censo de pacientes hospitalizados hoy con el censo de una fecha de referencia (hace un mes, un semestre o un año), con filtros por servicio y aseguradora. Sirve para ver si la ocupación actual está por encima o por debajo de la de periodos anteriores. Es una comparación entre dos fechas, no un acumulado del periodo.

## Fuentes de datos
- **PACIENTES POR ESTANCIA**: Estancias hospitalarias (HPNESTANC) con ingreso, cama, paciente, plan, servicio y aseguradora, cruzadas con cuatro fechas de corte: HOY, MES, SEMESTRE y AÑO. Una fila por rango e ingreso.

## Indicadores
- **Atenciones hoy**: Pacientes hospitalizados en la fecha de hoy. Medida ATENCIONES_HOY = CALCULATE(DISTINCTCOUNT('PACIENTES POR ESTANCIA'[ADNINGRES]), 'PACIENTES POR ESTANCIA'[RANGO] = "HOY").
- **Rango atenciones**: Pacientes hospitalizados en la fecha de corte del rango seleccionado. Cálculo por confirmar.
- **Total atenciones**: Total de ingresos de la tabla según los filtros. Cálculo por confirmar.

## Visuales
- **Tarjetas**: RANGO ATENCIONES y TOTAL ATENCIONES.
- **Selector RANGO**: Botones AÑO, MES y SEMESTRE.
- **Segmentadores**: SERVICIO y ASEGURADORA.
- **Comparativo censo**: Gráfico de líneas COMPARATIVO CENSO ACTUAL VS RANGO SELECCIONADO por servicio con dos series, RANGO (censo en la fecha de corte) y ATENCIONES_HOY (censo de hoy), con etiquetas de valor.

## Reglas de negocio
- **Fechas de corte**: MES es hoy menos 1 mes, SEMESTRE hoy menos 6 meses, AÑO hoy menos 12 meses y HOY la fecha actual.
- **Paciente en el censo**: Un ingreso entra en un rango si la fecha de corte está entre su fecha de ingreso a la estancia y su fecha de salida (o hoy si no ha salido).
- **Una fila por ingreso**: Si un ingreso tiene varias estancias en la fecha de corte, se toma la abierta o la más reciente.
- **Pacientes con documento**: Solo se incluyen pacientes con número de documento.

## Observaciones
- **Botones copiados**: La documentación describe botones de navegación por áreas copiados de DETALLE SOLICITUD CAMAS; la captura de esta página no los muestra. Por confirmar.
- **Acceso y nombre**: La página no está en la copia local del PBIP ni se enlaza desde INICIO en la documentación. Nombre de página en Power BI por confirmar.
- **Significado de «rango»**: El nombre sugiere un acumulado del periodo, pero la consulta mide el censo de un solo día (la fecha de corte).

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
