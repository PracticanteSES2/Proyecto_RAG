---
tablero: TABLERO CONTROL FACTURACION
pagina: FACTURACION IMAGENES
nombre_funcional: Tiempo de gestión en facturación de imágenes
bloque: Histórico
tablas: [FACTURACION PERFILES, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# FACTURACION IMAGENES

## Propósito
Muestra cuánto tardan las cuentas en el perfil FACTURACION IMAGENES, es decir en la facturación de imágenes diagnósticas: tiempo promedio, evolución por año y mes y comparación entre ingresos ambulatorios y hospitalarios. Análisis histórico; se llega desde el botón FACTURACION IMAGENES de RESUMEN FACTURACION. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **FACTURACION PERFILES**: Gestiones por cuenta y perfil (ver RESUMEN FACTURACION); esta página solo muestra el perfil FACTURACION IMAGENES (código 21) de cuentas con factura emitida. Egresos desde el 1 de agosto de 2025.

## Indicadores
- **Tiempo promedio de gestión de factura**: Promedio en horas de 'FACTURACION PERFILES'[TIEMPO], es decir de las horas entre que el perfil recibe la cuenta y la entrega. Agregación: promedio de la columna.
- **Tiempo hospitalario**: Medida TIEMPO_FACTURACION_HOSPITALIZACION = CALCULATE(AVERAGE('FACTURACION PERFILES'[TIEMPO]), 'FACTURACION PERFILES'[TIPO INGRESO] = "HOSPITALARIO"). Unidad: horas.
- **Tiempo ambulatorio**: Promedio de TIEMPO para TIPO INGRESO = "AMBULATORIO" (TIEMPO_FACTURACION_AMBULATORIO). Definición por confirmar; en la documentación aparece comentada.

## Visuales
- **Filtros**: Segmentadores SERVICIO, Año y Mes; botón de inicio (casa).
- **Tarjeta**: TIEMPO PROMEDIO GESTION FACTURA, en horas.
- **Gráfico de tiempo por mes**: Titulado «TIEMPO GESTION FACTURACION»; tiempo promedio de gestión por año y mes.
- **Gráfico ambulatorio y hospitalario**: Titulado «TIEMPO FACTURACION AMBULATORIO Y HOSPITALARIO»; líneas TIEMPO AMBULATORIO y TIEMPO HOSPITALARIO por año y mes.

## Reglas de negocio
- **Filtro de página**: PERFIL = «FACTURACION IMAGENES» y ESTADO_FACTURA = «FACTURADA». Por confirmar en esta página; es el patrón de las páginas de perfil que trae el PBIP.
- **Primera gestión**: Para cada cuenta se toma la primera vez que el perfil la recibió y la entrega correspondiente.

## Observaciones
- **Página EN PROCESO relacionada**: Las cuentas de este perfil que siguen abiertas se ven en EN PROCESO FACTURACION IMAGENES.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
