---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: GINECO
nombre_funcional: Ingresos por maternidad (gineco) por mes y año
bloque: Histórico
tablas: [ATENCIONES_GINECO, ASEGURADORAS]
actualizado: 2026-10-28
version: 2
---

# GINECO

## Propósito
Muestra cuántas atenciones de ginecología (ingresos con causa maternidad) hay cada mes y compara los años mes a mes. Desde qué botón se llega: por confirmar.

## Fuentes de datos
- **ATENCIONES_GINECO**: Ingresos desde 2023-01-01 hasta hoy con causa de ingreso 9 (maternidad), uno por paciente, ingreso y fecha; trae número de ingreso, plan de beneficio, fecha y hora de ingreso y aseguradora agrupada. Se relaciona con ASEGURADORAS; no se relaciona con el Calendario.

## Indicadores
- **Atenciones en gineco**: Número de ingresos por mes y año. Medida o columna contada por confirmar.

## Visuales
- **Segmentadores**: ASEGURADORA, Año y Mes.
- **Gráfico de atenciones por mes y año**: Columnas «ATENCIONES EN GINECO por Mes y Año» agrupadas por mes, con una columna por año.
- **Tabla de detalle anual**: Matriz de atenciones por año (filas) y mes (columnas).
- **Botón de inicio**: Botón de casa que vuelve a INDICADORES.

## Reglas de negocio
- **Atención en gineco**: Ingreso con causa de ingreso 9 (maternidad), sin importar el área de servicio.
- **Agrupación de aseguradoras**: NUEVA EPS, SURA (sin ARL SURA, seguros de vida ni Suramericana), SANITAS (sin Colsanitas ni Medisanitas) y MALLAMAS; el resto conserva su nombre.

## Observaciones
- **Nombre de página**: El PBIP actual no trae una página con este nombre; la página existe en la documentación del propietario. Por confirmar su nombre en Power BI.
- **Sin relación con el Calendario**: La tabla no se une al Calendario; los segmentadores Año y Mes deben salir de la fecha de ingreso de la propia tabla. Por confirmar.
- **Sin medidas documentadas**: El documento no lista medidas ni dice qué se cuenta.
- **Ingresos no excluidos**: A diferencia de urgencias, esta consulta no excluye ingresos por estado (AINESTADO).

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
