---
tablero: TABLERO REFERENCIA
pagina: INICIO
nombre_funcional: Resumen de solicitudes de referencia recibidas
bloque: Día
tablas: [REFERENCIA]
actualizado: 2026-10-28
version: 2
---

# INICIO

## Propósito
Página principal del tablero. Resume las solicitudes de referencia recibidas en los últimos 30 días: cantidad, tiempo promedio de respuesta, edad promedio, solicitudes por especialidad, por rango de tiempo de respuesta y por causa de no aceptación. Es de seguimiento reciente (bloque Día). Desde aquí se navega a NO ACEPTADOS RECEPCIÓN, ACEPTADOS RECEPCIÓN y REMISIÓN. En Power BI la página se llama INICIO.

## Fuentes de datos
- **REFERENCIA**: Solicitudes de recepción con llamada en los últimos 30 días; incluye paciente, edad, fechas de llamada, llegada estimada, ingreso, aceptación y no aceptación, servicio, prestador, EPS, estado, causa, motivo, especialidad (GEEDESCRI) y usuarios que registran y aceptan.

## Indicadores
- **Cantidad de solicitudes**: Número de solicitudes de referencia del periodo filtrado. Medida exacta por confirmar (conteo de REFERENCIA[OID]).
- **Tiempo promedio de respuesta**: Promedio en horas de REFERENCIA[TIEMPO_REMISION] (llamada hasta no aceptación, aceptación u hoy). Agregación por confirmar.
- **Promedio de edad**: Promedio en años de REFERENCIA[ANOS]. Agregación por confirmar.

## Visuales
- **Tarjetas**: CANTIDAD DE SOLICITUDES, TIEMPO PROMEDIO RESPUESTA y PROMEDIO DE EDAD.
- **Filtros**: Segmentadores de EPS y ESTADO y control deslizante de rango de fechas de la llamada.
- **Tabla de especialidades**: Columnas ESPECIALIDAD, SOLICITUDES y % DEL TOTAL, con fila de total.
- **Gráfico circular por tiempo**: Titulado «SOLICITUDES por TIEMPO»; solicitudes según RANGO_REMISION (0-24, 24-72, 72-120 y más de 120 horas).
- **Gráfico circular por causa**: Titulado «SOLICITUDES por CAUSA NO ACEPTACIÓN»; solicitudes según CAUSA_MAYUSC; la porción «(En blanco)» son solicitudes sin causa de no aceptación.
- **Botones de navegación**: NO ACEPTADOS RECEPCIÓN, ACEPTADOS RECEPCIÓN y REMISIÓN.

## Reglas de negocio
- **Rangos de tiempo**: 0-24 HORAS de 0 a 24 horas; 24-72 HORAS de más de 24 a 72; 72-120 HORAS de más de 72 a 120; MAYOR A 120 HORAS de más de 120.

## Observaciones
- **Especialidad vacía**: En la captura de la documentación la fila sin especialidad es la mayor de la tabla (41,78 %); por confirmar por qué tantas solicitudes no tienen especialidad.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
