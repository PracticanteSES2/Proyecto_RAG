---
tablero: TABLERO LAVANDERIA
pagina: Página 1
nombre_funcional: Peso mensual de ropa por servicio, colaborador y turno
bloque: Histórico
tablas: [LAVANDERIA]
actualizado: 2026-10-28
version: 2
---

# Página 1

## Propósito
Única página del tablero; en Power BI se llama «Página 1». Muestra por mes el peso de ropa recibido por servicio y su porcentaje de participación, el peso registrado por cada colaborador, la distribución por turno y el total mensual. Sirve para analizar la carga de lavandería en el tiempo, con filtros de año y mes.

## Fuentes de datos
- **LAVANDERIA**: Pesajes de ropa con peso, fecha, turno, servicio y usuario que registra; todo el histórico.

## Indicadores
- **Peso**: Peso total de ropa registrado: suma de LAVANDERIA[Peso] en el contexto del visual. La unidad (kilogramos o libras) no está documentada; por confirmar.
- **Participación por servicio**: Peso del servicio dividido entre el peso total del mismo mes, en porcentaje (visual PESO y % PARTICIPACION de la matriz). No es una medida del modelo; se calcula en el visual.
- **Peso por turno**: Peso total de cada turno (LAVANDERIA[TURNO_OK]) y su porcentaje sobre el total, en el gráfico circular PESO por TURNO.
- **Peso registrado por colaborador**: Peso total que registró cada colaborador (LAVANDERIA[NOMBRE_COMPLETO]) en cada mes, en la matriz USUARIO QUE REGISTRA.
- **Peso total mensual**: Suma de LAVANDERIA[Peso] por mes en las columnas de PESO TOTAL por Mes.

## Visuales
- **Segmentadores**: Año y Mes.
- **Matriz de participación por servicio**: Servicios en filas y meses en columnas, con PESO y % PARTICIPACION de cada mes y fila de total.
- **Matriz USUARIO QUE REGISTRA**: Colaboradores en filas y meses en columnas con el peso registrado y total.
- **PESO por TURNO**: Torta con el peso y porcentaje de MAÑANA, TARDE, NOCHE y (En blanco).
- **PESO TOTAL por Mes**: Columnas con el peso total de cada mes.

## Reglas de negocio
- **Participación mensual**: El porcentaje de participación de cada servicio se calcula dentro de cada mes; cada mes suma 100 %.

## Observaciones
- **Filtro de aseguradora inexistente**: La documentación dice que hay filtro por Aseguradora, pero la página solo tiene Año y Mes.
- **Fecha de los filtros**: No está documentado si Año y Mes usan Fecha (encabezado) o FechaRegistro (pesaje). Por confirmar.
- **Turno en blanco**: Una parte del peso aparece como (En blanco) en el gráfico de turnos: pesajes con turno distinto de 1, 2 o 3 o sin turno.
- **Usuario en blanco**: La matriz de usuarios muestra una fila sin nombre: pesajes sin usuario asociado.
- **PBIP sin visuales**: El PBIP local solo trae la página «Página 1» sin visuales ni segmentadores; los visuales descritos provienen de la documentación del propietario y están por confirmar contra el informe publicado.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe; la página se renombra a «Página 1» como en el PBIP.
