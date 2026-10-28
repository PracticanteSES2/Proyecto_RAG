---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: INDICADORES
nombre_funcional: Egresos, estancia, ocupación y giro cama institucionales
bloque: Histórico
tablas: [FACT_EGRESOS, FACT_ESTANCIA, PORCENTAJE_OCUPACIONAL, DIM_SERVICIO, TERCERO, Calendario]
actualizado: 2026-10-28
version: 2
id_pagina: 6c03bc7bd793eda6c68a
---

# INDICADORES

## Propósito
Página principal del tablero. Muestra mes a mes, comparando los dos últimos años, los egresos, el promedio de estancia, el porcentaje ocupacional y el giro cama de la institución o de una vista de servicios. Desde aquí se navega a las páginas de cada servicio.

## Fuentes de datos
- **FACT_EGRESOS**: Egresos con ingreso, entidad, cama, servicio, servicio homologado, tipo de egreso (EGRESO_PUERTA) y fechas de epicrisis y de facturación; se une al Calendario por la fecha de egreso de facturación.
- **FACT_ESTANCIA**: Estancias por cama con días y horas de estancia y servicio homologado.
- **PORCENTAJE_OCUPACIONAL**: Ocupación de camas por día (cama, servicio, fecha) para el cálculo del porcentaje ocupacional.

## Indicadores
- **Egresos**: Número de egresos del periodo. Medida del modelo Total Egresos = COUNTROWS(FACT_EGRESOS). Por confirmar que sea la de la tarjeta y el gráfico.
- **Capacidad instalada**: Número de camas instaladas que muestra la tarjeta CAPACIDAD INSTALADA. Medida por confirmar.
- **Promedio de estancia**: Días de estancia por egreso. Medida del modelo PROMEDIO_ESTANCIA = DIVIDE([ESTANCIA_VALIDADA], [Total Egresos], BLANK()). Por confirmar que sea la del gráfico.
- **Estancia validada**: Suma de días de estancia; en URGENCIAS, URGENCIAS SALA AZUL, BOTON AZUL 3 PISO y URGENCIAS BOTON AZUL suma horas y las divide entre 24 (medida ESTANCIA_VALIDADA).
- **Porcentaje ocupacional**: Días cama ocupados entre días cama disponibles. Medida del modelo PORCENTAJE_OCUPACIONAL_TOTAL: conteo de registros de ocupación dividido por la suma, por servicio, de camas del servicio × días del mes. Por confirmar que sea la del gráfico.
- **Giro cama**: Egresos por cama. Medida GIRO_CAMA1 (confirmada en el PBIP): ingresos distintos con egreso tipo PUERTA o TRASLADO divididos entre la suma de camas de los servicios (NUM_CAM_EGRESOS).

## Visuales
- **Segmentadores**: ASEGURADOR (TERCERO[TERNOMCOM]), Año, Mes y SERVICIO (DIM_SERVICIO[SERVICIO_HOMOLOGADO]).
- **Tarjetas de egresos y camas**: «EGRESOS» y «CAPACIDAD INSTALADA».
- **Botones de vista**: INSTITUCIONAL, URGENCIAS, GINECO, NEONATOS, HOSPITALIZACIÓN, UCI/UCIN, UCI y UCIN; son marcadores que cambian la vista de los gráficos de esta misma página.
- **Botón PUERTA**: Botón sobre el gráfico de egresos. Función por confirmar.
- **Gráfico de egresos**: Líneas «EGRESOS» por mes, una línea por año (últimos dos años).
- **Gráfico de promedio de estancia**: Líneas «PROMEDIO ESTANCIA» por mes, una línea por año.
- **Gráfico de porcentaje ocupacional**: Líneas «PORCENTAJE OCUPACIONAL» por mes, una línea por año.
- **Gráfico de giro cama**: Líneas «GIRO CAMA» con GIRO_CAMA1 por mes, una línea por año.
- **Botones de navegación**: TRIAGES, URGENCIAS, IMAGENES, SES EN TU HOGAR, CANCEROLOGÍA, PERIOPERATORIA, GINECO-OBSTETRICIA, HOSPITALIZACIÓN PARCIAL, CONSULTA AMBULATORIA, UNIDAD CARDIONEUROVASCULAR, LABORATORIO CLÍNICO y LABORATORIO DE PATOLOGÍA.

## Reglas de negocio
- **Servicios ocultos en el segmentador**: SERVICIO no ofrece ATENCION DOMICILIARIA, BLOQUEADO, BLOQUEAR-CUIDADO INTERMEDIO ADULTO, BLOQUEAR-UNIDAD POLIVALENTE, CAMAS MAL CREADAS EN EL SISTEMA, CIRUGIA GENERAL, CUIDADO ESPECIAL, ENDOSCOPIA TERAPEUTICA, HOSPITALIZACIÓN CUIDADO ESPECIAL (3 SUR), IMAGENES, QUIROFANO, SERVICIOS DE HOSPITALIZACIÓN EN EL DOMICILIO, UNIDAD RECIEN NACIDOS, UNIDAD CARDIO NEURO VASCULAR ni el valor vacío.
- **Servicios fuera del giro cama**: El gráfico de giro cama excluye CIRUGIA GENERAL, HOSPITALIZACION PARCIAL, SERVICIOS DE HOSPITALIZACIÓN EN EL DOMICILIO, URGENCIAS 2 SUR y el servicio vacío.
- **Camas para giro cama**: BOTON AZUL 3 PISO 6, HOSP 2 SUR 21, HOSP 4 NORTE 23, HOSP 4 SUR 21, HOSP 5 NORTE 12, HOSP 5 SUR 19, HOSPITALIZACION 6 PISO 16, HOSPITALIZACION NEONATOS 16, HOSPITALIZACION PARCIAL 8, CUIDADO INTERMEDIO NORTE 21, CUIDADO INTERMEDIO SUR 17, OBSTETRICIA CRITICA 4, UNIDAD OBSTETRICIA 26, UNIDAD DE CUIDADO INTENSIVO 20, URGENCIAS 54 y URGENCIAS SALA AZUL 9 (medida NUM_CAM_EGRESOS; por confirmar).
- **Camas para ocupación**: CUARTO PISO NORTE 23, CUARTO PISO SUR 21, CUIDADO INTERMEDIO NORTE 21, CUIDADO INTERMEDIO SUR 17, HOSPITALIZACION NEONATOS 16, OBSTETRICIA 26, OBSTETRICIA CRITICO 4, QUINTO PISO NORTE 12, QUINTO PISO SUR 19, SEGUNDO PISO SUR 21, SEXTO PISO 16, UNIDAD DE CUIDADO INTENSIVO 20, URGENCIAS EXPANSION 27, URGENCIAS 54 y URGENCIAS BOTON AZUL 9 (medida NUMERO_CAMAS; por confirmar).
- **Egresos para giro cama**: Solo cuentan los egresos con EGRESO_PUERTA igual a PUERTA o TRASLADO.

## Observaciones
- **Nombre de página**: En Power BI la página se llama INDICADORES; la documentación del propietario la titula «INICIO».
- **PBIP incompleto**: El PBIP solo trae el gráfico de giro cama, los segmentadores y algunos botones; las medidas de los demás gráficos y tarjetas salen del catálogo del modelo. Por confirmar.
- **Capacidad instalada sin cuadrar**: Las camas de NUM_CAM_EGRESOS suman 293 y las de NUMERO_CAMAS 306; ninguna coincide con el valor de la tarjeta en la captura (308). Por confirmar.
- **Unidad del promedio de estancia**: En la captura el gráfico muestra valores entre 118 y 148, que no parecen días por egreso. Por confirmar la unidad.
- **Ocupación sobre 100 %**: En la captura el porcentaje ocupacional supera 100 % en varios meses y cae en el mes en curso por estar incompleto.
- **Filtro sobrante**: El segmentador SERVICIO tiene un filtro oculto sobre CONSULTA_URGENCIAS[ASEGURADORA] que no corresponde a esta página.
- **Listas de camas distintas**: Giro cama y ocupación usan listas de camas con nombres de servicio diferentes (HOSP 4 NORTE frente a CUARTO PISO NORTE).

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
