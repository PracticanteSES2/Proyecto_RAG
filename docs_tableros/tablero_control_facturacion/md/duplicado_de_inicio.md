---
tablero: TABLERO CONTROL FACTURACION
pagina: Duplicado de INICIO
nombre_funcional: Copia de trabajo de INICIO con gestiones por usuario y monto facturado
bloque: Histórico
tablas: [FACTURACION PERFILES, ULT_GESTION, INGRESOS, DIM_PERFIL, CALENDARIO, DIM_TIPO_INGRESO]
actualizado: 2026-10-28
version: 1
---

# Duplicado de INICIO

## Propósito
Copia de INICIO que mezcla indicadores de INICIO y de la página PROCESO FACTURACION de la documentación: gestiones por usuario, tiempo de gestión por mes, monto facturado, ingresos abiertos y monto por servicio. Página oculta en Power BI; ningún botón lleva a ella. Parece una versión de trabajo de PROCESO FACTURACION, por confirmar. Sus botones llevan a RESUMEN FACTURACION, FACTURACION, TRAZABILIDAD_H-A y FACTURACION PENDIENTE.

## Fuentes de datos
- **FACTURACION PERFILES**: Alimenta la tabla de gestiones por usuario y el gráfico de tiempo de gestión por mes.
- **ULT_GESTION**: Alimenta las tarjetas MONTO FACTURADO e INGRESOS ABIERTOS y las barras por servicio.
- **INGRESOS**: Solo se usa en filtros de visual de la tarjeta INGRESOS ABIERTOS.

## Indicadores
- **Gestiones**: Número de ingresos distintos gestionados por cada persona: DISTINCTCOUNT(FACTURACION PERFILES[INGRESO]) por NOMBRE_COMPLETO (quien entrega la cuenta)
- **Tiempo de gestión**: Promedio mensual de FACTURACION PERFILES[TIEMPO], en horas (siempre múltiplos de 24)
- **Monto facturado**: SUM(ULT_GESTION[SFANETOFAC]), columna que no existe en el modelo actual; el monto está en ULT_GESTION[MONTO_FACTURADO]. La tarjeta y las barras que la usan no se pueden calcular.
- **Ingresos abiertos**: DISTINCTCOUNT(ULT_GESTION[INGRESO]), con filtros de visual sobre INGRESOS que probablemente no la afectan.

## Visuales
- **Tabla de gestiones**: Tabla «NOMBRE COMPLETO» y GESTIONES, ordenada por nombre, sin nombres vacíos.
- **Tarjetas**: MONTO FACTURADO e INGRESOS ABIERTOS.
- **Filtros**: Segmentadores «Date Año» (solo 2025 y 2026) y «Date Mes» (CALENDARIO[Date]), «PERFIL» (DIM_PERFIL[PERFIL]) y «TIPO_INGRESO» (DIM_TIPO_INGRESO[TIPO_INGRESO])
- **Gráfico de líneas por mes**: Gráfico de líneas con «Date Mes» y la serie TIEMPO DE GESTIÓN (promedio de TIEMPO)
- **Barras por servicio**: Gráfico de barras agrupadas «MONTO FACTURADO POR SERVICIO»: suma de SFANETOFAC por AREA_SERVICIO y tipo de ingreso, sin áreas vacías.
- **Botones de navegación**: DETALLE FACTURACIÓN (RESUMEN FACTURACION), PROCESO FACTURACIÓN (FACTURACION), TRAZABILIDAD (TRAZABILIDAD_H-A) y FACTURACION PENDIENTE.

## Reglas de negocio
- **Filtros de página**: FACTURACION PERFILES[TIPO INGRESO] = HOSPITALARIO y FACTURACION PERFILES[TIEMPO] mayor o igual a 0 (confirmado en el PBIP); solo afectan a lo que usa FACTURACION PERFILES.

## Observaciones
- **Columna fuera del modelo**: ULT_GESTION[SFANETOFAC] no existe en el modelo: la tarjeta MONTO FACTURADO y las barras por servicio quedan rotas o vacías. Por confirmar.

## Historial de cambios
- **2026-10-28 · v1**: Página documentada a partir del modelo y del informe.
