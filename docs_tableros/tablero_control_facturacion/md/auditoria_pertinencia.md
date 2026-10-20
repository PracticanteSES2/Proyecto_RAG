---
tablero: TABLERO CONTROL FACTURACION
pagina: AUDITORIA PERTINENCIA
nombre_funcional: Tiempo de gestión en auditoría de pertinencia
bloque: Histórico
tablas: [FACTURACION PERFILES, CALENDARIO, DIM_TIPO_INGRESO]
actualizado: 2026-10-20
version: 1
---

# AUDITORIA PERTINENCIA

## Propósito
Muestra cuánto tardan las cuentas en el perfil AUDITORIA PERTINENCIA, es decir en la auditoría de pertinencia: tiempo promedio, evolución por año y mes y comparación entre ingresos ambulatorios y hospitalarios. Análisis histórico; se llega desde el botón AUDITORIA PERTINENCIA de RESUMEN FACTURACION. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **FACTURACION PERFILES**: Gestiones por cuenta y perfil (ver RESUMEN FACTURACION); esta página solo muestra el perfil AUDITORIA PERTINENCIA (código 4) de cuentas con factura emitida. Egresos desde el 1 de agosto de 2025.

## Indicadores
- **Tiempo promedio de gestión de factura**: Promedio en horas de 'FACTURACION PERFILES'[TIEMPO], es decir de las horas entre que el perfil recibe la cuenta y la entrega. Agregación: promedio de la columna.
- **Tiempo hospitalario**: Medida TIEMPO_FACTURACION_HOSPITALIZACION = CALCULATE(AVERAGE('FACTURACION PERFILES'[TIEMPO]), 'FACTURACION PERFILES'[TIPO INGRESO] = "HOSPITALARIO"). Unidad: horas.
- **Tiempo ambulatorio**: Promedio de TIEMPO para TIPO INGRESO = "AMBULATORIO" (TIEMPO_FACTURACION_AMBULATORIO). Definición por confirmar; en la documentación aparece comentada.

## Visuales
- **Filtros**: Segmentadores SERVICIO, Año y Mes y botones AMBULATORIO / HOSPITALARIO (DIM_TIPO_INGRESO[TIPO_INGRESO]); botón de inicio (casa).
- **Tarjeta**: TIEMPO PROMEDIO GESTION FACTURA, en horas.
- **Gráfico de tiempo por mes**: Titulado «TIEMPO GESTION FACTURACION»; tiempo promedio de gestión por año y mes.
- **Gráfico ambulatorio y hospitalario**: Titulado «TIEMPO FACTURACION AMBULATORIO Y HOSPITALARIO»; líneas TIEMPO AMBULATORIO y TIEMPO HOSPITALARIO por año y mes.

## Reglas de negocio
- **Filtro de página**: PERFIL = «AUDITORIA PERTINENCIA» y ESTADO_FACTURA = «FACTURADA». Por confirmar en esta página; es el patrón de las páginas de perfil que trae el PBIP.
- **Primera gestión**: Para cada cuenta se toma la primera vez que el perfil la recibió y la entrega correspondiente.
- **Recibe y entrega en auditoría**: Para este perfil, recibe es la asignación (estado 2) y entrega es la respuesta (estado 4) de la solicitud de auditoría (servicio categoría 374).

## Observaciones
- **Página EN PROCESO relacionada**: Las cuentas de este perfil que siguen abiertas se ven en EN PROCESO AUDITORIA PERTINENCIA.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
