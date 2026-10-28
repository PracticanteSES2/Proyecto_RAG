---
tablero: TABLERO PERFIL DE MORBILIDAD
pagina: PIRAMIDE POBLACIONAL
nombre_funcional: Pirámide poblacional de los pacientes egresados por edad y sexo
bloque: Histórico
tablas: [MATRIZ 2024, ONCOLOGICO]
actualizado: 2026-10-28
version: 2
---

# PIRAMIDE POBLACIONAL

## Propósito
Pirámide poblacional de los pacientes egresados: porcentaje de pacientes por rango de edad y sexo, con el total de mujeres y de hombres. Sirve para conocer la composición demográfica de la población atendida y planear servicios. Se llega desde el botón PIRAMIDE POBLACIONAL de INICIO. Análisis por año y mes (bloque Histórico).

## Fuentes de datos
- **MATRIZ 2024**: Egresos con edad, rango de edad, sexo, GRD y servicio.
- **ONCOLOGICO**: Marca de diagnóstico oncológico para el botón ONCOLOGICO.

## Indicadores
- **Mujeres**: Egresos de sexo femenino. SUM(MATRIZ 2024[MUJERES]); MUJERES = IF('MATRIZ 2024'[Sexo]="FEMENINO",1,0).
- **Hombres**: Egresos de sexo masculino. SUM(MATRIZ 2024[HOMBRES]); HOMBRES = IF('MATRIZ 2024'[Sexo]="MASCULINO",1,0).
- **Porcentaje por rango y sexo**: Egresos de cada rango de edad y sexo sobre el total de egresos filtrados, en porcentaje.

## Visuales
- **Pirámide por edad y sexo**: Gráfico de barras enfrentadas titulado «%PACIENTES ATENDIDOS por RANGO EDAD y SEXO»; FEMENINO a la izquierda y MASCULINO a la derecha, un rango de edad por fila (de 0-9 años abajo a 99 años y más arriba).
- **Filtros de la página**: Segmentador de GRD, botón ONCOLOGICO, botones de servicio (GINECO, HOSPITALIZACION, HOSPITALIZACION PARCIAL, NEONATOS, SALA AZUL, UCI/UCIN, URGENCIAS) y listas de RANGO EDAD, Mes y Año.
- **Tarjetas de mujeres y hombres**: Totales de egresos de cada sexo.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Rangos de edad**: Decenios de 0-9 a 80-89 años, luego 90-98 años y 99 años y más, según MATRIZ 2024[rango_edad].
- **Base del porcentaje**: El porcentaje se calcula sobre el total general de egresos con los filtros aplicados, no sobre cada sexo; en la captura de la documentación los porcentajes de ambos lados suman 100 %.

## Observaciones
- **Sexo sin dato**: Los egresos sin sexo FEMENINO ni MASCULINO no cuentan en las tarjetas ni en la pirámide.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP (solo modelo semántico).
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
