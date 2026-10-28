---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: PORCENTAJE OCUPACIONAL
nombre_funcional: Porcentaje de ocupación de camas por mes y servicio
bloque: Histórico
tablas: [PORCENTAJE_OCUP, Calendario]
actualizado: 2026-10-28
version: 2
---

# PORCENTAJE OCUPACIONAL

## Propósito
Muestra el porcentaje de ocupación de camas mes a mes desde 2023 y el de cada servicio, para seguir la ocupación hospitalaria en el tiempo. Desde qué botón se llega: por confirmar.

## Fuentes de datos
- **PORCENTAJE_OCUP**: Una fila por cama y día con código de cama, fecha, servicio y estado, armada desde la tabla de estados de camas (estados_camas) de la bodega DWSES y la de camas ocupadas; se une al Calendario por fecha.

## Indicadores
- **Porcentaje ocupacional**: Días cama ocupados entre días cama contados. Cálculo: %OCUPACIONALC = SUM(PORCENTAJE_OCUP[OCUPADA])/SUM(PORCENTAJE_OCUP[DISPONIBLE]). Unidad: porcentaje.
- **Cama ocupada**: Columna OCUPADA = 1 si el estado es OCUPADA o 2.
- **Cama contada**: Columna DISPONIBLE = 1 si el estado es OCUPADA, DISPONIBLE, DESOCUPADA, MANTENIMIENTO, 1, 2 o 5.

## Visuales
- **Segmentadores**: SERVICIO, Año y Mes.
- **Gráfico de ocupación**: Líneas «PORCENTAJE OCUPACIONAL por Año y Mes» con el porcentaje de cada mes en un eje continuo de años y meses.
- **Tabla de detalle anual**: Matriz del porcentaje por año (filas) y mes (columnas).
- **Tabla por servicio**: Tabla SERVICIO y PORCENTAJE OCUPACIONAL con el porcentaje de cada servicio y el total.
- **Botón de inicio**: Botón de casa que vuelve a INDICADORES.

## Reglas de negocio
- **Estado de la cama**: Una cama es OCUPADA si aparece en camas ocupadas ese día; si no aparece pero tiene estado registrado, es DISPONIBLE.
- **Cuidado crítico obstétrico**: Toda cama o servicio cuyo nombre contiene «CRIT» se agrupa como CUIDADO CRÍTICO OBSTETRICO (columna servicio_uni y la consulta).
- **Camas en mantenimiento**: Las camas en mantenimiento cuentan en el denominador.

## Observaciones
- **Nombre de página**: El PBIP actual no trae una página con este nombre; la página existe en la documentación del propietario. Por confirmar su nombre en Power BI.
- **Consulta incompleta**: La consulta del documento está cortada en la unión con la tabla de camas ocupadas.
- **Regla CRIT amplia**: Cualquier servicio con «CRIT» en el nombre (por ejemplo una unidad de cuidado crítico no obstétrica) quedaría como CUIDADO CRÍTICO OBSTETRICO. Por confirmar.
- **Distinto a INICIO**: INDICADORES calcula la ocupación con otra tabla (PORCENTAJE_OCUPACIONAL) y camas fijas por servicio; los porcentajes de las dos páginas no coinciden.
- **Estados numéricos**: No se documenta qué significan los estados 1, 2 y 5. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
