---
tablero: TABLERO PERFIL DE MORBILIDAD
pagina: GENERAL
nombre_funcional: Perfil epidemiológico de los egresos hospitalarios
bloque: General
tablas: [MATRIZ 2024, FACTURACION, ONCOLOGICO, AMBULATORIO, PERIOPERATORIA, Calendario]
actualizado: 2026-10-20
version: 1
---

# GENERAL

## Propósito
Describe el perfil de morbilidad de la población atendida: egresos por diagnóstico (CIE10), grupo relacionado por diagnóstico (GRD) y categoría diagnóstica mayor (CMD), con edad, sexo, servicio, mortalidad y facturación. Sirve para identificar las patologías que generan más demanda y orientar recursos. La página INICIO lleva a PIRAMIDE POBLACIONAL, FACTURACION y DETALLE PERFIL DE MORBILIDAD, y también a páginas de perioperatoria y atenciones ambulatorias. Todas las tablas son importadas y el análisis es por año y mes.

## Fuentes de datos
- **MATRIZ 2024**: Egresos hospitalarios, una fila por egreso. Une la matriz histórica de egresos (DW_MATRIZ_EGRESOS) con los egresos del tablero GRD (TABLEROGRD) con salida desde 2025-01-01; trae edad, sexo, asegurador, diagnósticos CIE10, CMD y GRD de ingreso y de egreso, banderas de servicio, estado del egreso y tipo de salida. Modo import.
- **FACTURACION**: Valor neto de las facturas (SFANETOFAC) por número de ingreso, para ingresos desde 2024-01-01 con estado distinto de 2 y 4, facturas en estado 1 y no anuladas. Se relaciona con MATRIZ 2024 por ingreso (muchos a muchos, en ambos sentidos). Modo import.
- **ONCOLOGICO**: Catálogo de diagnósticos CIE10 con su GRD, su CMD y la marca ONCOLOGICO o NO ONCOLOGICO según la tabla de relación de diagnósticos. Filtra MATRIZ 2024 por el código CIE10 calculado. Modo import.
- **AMBULATORIO**: Consultas ambulatorias cumplidas (estado 2) desde 2024-01-01 con diagnóstico principal, especialidad agrupada, primera vez o control y GRD. Excluye consultas prioritarias, algunas especialidades y médicos. Modo import.
- **PERIOPERATORIA**: Cirugías (CIRUGIAS_DWSES) con diagnóstico, CMD, GRD, edad a la fecha de cirugía y asegurador. Modo import.
- **Calendario**: Tabla calculada CALENDAR("2024-01-01", 31 de diciembre del año actual); filtra MATRIZ 2024 por su columna fecha y PERIOPERATORIA por fecha de cirugía.

## Definiciones
- **Egreso o atención**: Una fila de MATRIZ 2024. Las páginas lo llaman EGRESOS, ATENCIONES o PACIENTES ATENDIDOS.
- **CIE10**: Diagnóstico de la Clasificación Internacional de Enfermedades. MATRIZ 2024[CIE10_R] muestra la descripción del egreso y, si falta, la del ingreso, con la primera letra en mayúscula.
- **GRD**: Grupo relacionado por diagnóstico. MATRIZ 2024[GRD_R] toma el GRD de ingreso si el paciente pasó por urgencias y el de egreso en los demás casos; corrige el texto «DOLRO ABDOMINA» a «Dolor Abdominal».
- **CMD**: Categoría diagnóstica mayor. MATRIZ 2024[CMD_R] usa la CMD de ingreso en urgencias y la de egreso en los demás; si el GRD es «Neoplasia maligna de retroperitoneo» la cambia a «Sistema Digestivo».
- **Servicio**: MATRIZ 2024[SERVICIOS] asigna un solo servicio con esta prioridad: URGENCIAS, SALA AZUL, HOSPITALIZACION, UCI/UCIN, NEONATOS, HOSPITALIZACION PARCIAL y GINECO.
- **Rango de edad**: MATRIZ 2024[rango_edad] en decenios de 0-9 a 80-89 años, luego 90-98 años y 99 años y más.
- **Defunción**: MATRIZ 2024[DEFUNCIONES] vale 1 cuando el estado del egreso es «FALLECE» o «1».
- **Tipo de salida**: PUERTA (código 1), TRASLADO (código 2) u OTRO; solo existe para los egresos de 2025 en adelante.
- **Oncológico**: Diagnóstico marcado como oncológico en la tabla de relación de diagnósticos (ONCOLOGICO[ONCOLOGICO]).

## Reglas de negocio
- **Periodo de los egresos**: La matriz histórica aporta los egresos anteriores y TABLEROGRD los de fecha de salida desde 2025-01-01.
- **Fecha de los egresos**: MATRIZ 2024[fecha] se arma con año y mes, así que los filtros de fecha solo distinguen meses (cada egreso queda en el día 1 del mes).
- **Agrupación de servicios en TABLEROGRD**: Para los egresos de 2025 en adelante el SQL marca Urgencias, Sala azul (BOTON AZUL), Hospitalización (HOSP… o HOSPITALIZACION…), UCI/UCIN (cuidado intensivo e intermedio), Neonatos (recién nacidos), Hospitalización parcial y Gineco (obstetricia y ginecología) según el nombre del servicio.
- **Código CIE10 calculado**: MATRIZ 2024[COD_CIE10_R] usa el código de ingreso si el paciente pasó por urgencias y el de egreso en los demás casos; con él se relaciona ONCOLOGICO.

## Observaciones
- **Páginas sin documentación**: INICIO tiene botones PERIOPERATORIA y ATENCIONES AMBULATORIAS, cuyas páginas no están en la documentación del propietario ni hay PBIP del informe; no se documentaron.
- **Sin informe PBIP**: Solo existe el modelo semántico (TMDL); los visuales se describen con la documentación y sus capturas y los campos exactos de cada visual quedan por confirmar.
- **Número de ingreso distinto por origen**: En los egresos de TABLEROGRD la columna Ingreso es el identificador interno del ingreso, mientras FACTURACION usa el consecutivo (AINCONSEC); la facturación de esos egresos podría no cruzar. Por confirmar.
- **Posibles duplicados**: Si la matriz histórica también trae egresos de 2025, se sumarían a los de TABLEROGRD; y la unión con epicrisis puede repetir egresos con más de una epicrisis. Por confirmar.
- **Descripción y código CIE10 desalineados**: Para pacientes de urgencias el código CIE10 calculado es el de ingreso, pero la descripción (CIE10_R) prioriza la de egreso.
- **Condición de urgencias amplia**: GRD_OK y COD_CIE10_R exigen que el paciente pase por urgencias y que alguna otra bandera de servicio sea «NO», lo que casi siempre se cumple; en la práctica basta con haber pasado por urgencias.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP (solo modelo semántico).
