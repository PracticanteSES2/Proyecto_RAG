---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: ATENCIONES EN RADIOTERAPIA
nombre_funcional: Ingresos a radioterapia por mes y año
bloque: Histórico
tablas: [RADIOTERAPIA]
actualizado: 2026-10-20
version: 1
---

# ATENCIONES EN RADIOTERAPIA

## Propósito
Muestra cuántas atenciones (ingresos) hay en el servicio de radioterapia cada mes y compara los años mes a mes. Desde qué botón se llega: por confirmar (posiblemente CANCEROLOGÍA de INICIO).

## Fuentes de datos
- **RADIOTERAPIA**: Ingresos al área de servicio 117 (radioterapia) desde 2023-01-01 hasta hoy, sin ingresos con AINESTADO 2; trae ingreso, fecha de admisión, fecha, paciente y asegurador (plan de beneficio). No se relaciona con el Calendario.

## Indicadores
- **Atenciones en radioterapia**: Número de ingresos por mes y año. Medida o columna contada por confirmar.

## Visuales
- **Segmentadores**: ASEGURADOR, Año y Mes.
- **Gráfico de atenciones por mes y año**: Columnas «ATENCIONES EN RADIOTERAPIA» agrupadas por mes, con una columna por año.
- **Tabla de detalle anual**: Matriz de atenciones por año (filas) y mes (columnas).
- **Botón de inicio**: Botón de casa que vuelve a INICIO.

## Reglas de negocio
- **Atención en radioterapia**: Ingreso cuya área de servicio es 117; cada ingreso cuenta una vez.
- **Ingresos excluidos**: Solo se excluye AINESTADO 2 (urgencias excluye además el 4).

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Sin relación con el Calendario**: La tabla no se une al Calendario; los segmentadores Año y Mes deben salir de la fecha de la propia tabla. Por confirmar.
- **Columna sin uso**: SERVICIO QUE INGRESA siempre vale RADIOTERAPIA porque la consulta ya filtra el área 117.
- **Asegurador sin agrupar**: El asegurador es el nombre del plan de beneficio, sin la agrupación de aseguradoras de otras páginas.
- **Años del gráfico**: En la captura el gráfico solo muestra 2024 y 2025 y la tabla también 2023, que tiene datos solo desde mayo. Filtro del gráfico por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
