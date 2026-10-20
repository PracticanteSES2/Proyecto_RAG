---
tablero: TABLERO LAVANDERIA
pagina: LAVANDERIA
nombre_funcional: Peso mensual de ropa por servicio, colaborador y turno
bloque: Histórico
tablas: [LAVANDERIA]
actualizado: 2026-10-20
version: 1
---

# LAVANDERIA

## Propósito
Única página del tablero. Muestra por mes el peso de ropa recibido por servicio y su porcentaje de participación, el peso registrado por cada colaborador, la distribución por turno y el total mensual. Sirve para analizar la carga de lavandería en el tiempo, con filtros de año y mes.

## Fuentes de datos
- **LAVANDERIA**: Pesajes de ropa con peso, fecha, turno, servicio y usuario que registra; todo el histórico.

## Indicadores
- **Peso**: Peso total de ropa registrado. Suma de LAVANDERIA[Peso]; unidad por confirmar.
- **Participación por servicio**: Peso del servicio sobre el peso total del mes, en porcentaje.
- **Peso por turno**: Peso total de cada turno y su porcentaje sobre el total.

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
- **Nombre de página**: La documentación no da el nombre de la página. Nombre de página en Power BI por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
