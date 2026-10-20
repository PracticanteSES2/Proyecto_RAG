---
tablero: TABLERO CONTROL FACTURACION
pagina: ESCANEO FOTOCOPIAS
nombre_funcional: Tiempo de gestión en escaneo de fotocopias
bloque: Histórico
tablas: [FACTURACION PERFILES, CALENDARIO, DIM_TIPO_INGRESO]
actualizado: 2026-10-20
version: 1
---

# ESCANEO FOTOCOPIAS

## Propósito
Muestra cuánto tardan las cuentas en el perfil ESCANEO FOTOCOPIAS, es decir en el escaneo y la digitalización de los documentos de la cuenta: tiempo promedio, evolución por año y mes y comparación entre ingresos ambulatorios y hospitalarios. Análisis histórico; se llega desde el botón ESCANEO FOTOCOPIAS de RESUMEN FACTURACION.

## Fuentes de datos
- **FACTURACION PERFILES**: Gestiones por cuenta y perfil (ver RESUMEN FACTURACION); esta página solo muestra el perfil ESCANEO FOTOCOPIAS (código 10) de cuentas con factura emitida. Egresos desde el 1 de agosto de 2025.

## Indicadores
- **Tiempo promedio de gestión de factura**: Promedio en horas de 'FACTURACION PERFILES'[TIEMPO], es decir de las horas entre que el perfil recibe la cuenta y la entrega. Agregación: promedio de la columna.
- **Tiempo hospitalario**: Medida TIEMPO_FACTURACION_HOSPITALIZACION = CALCULATE(AVERAGE('FACTURACION PERFILES'[TIEMPO]), 'FACTURACION PERFILES'[TIPO INGRESO] = "HOSPITALARIO"). Unidad: horas.
- **Tiempo ambulatorio**: Promedio de TIEMPO para TIPO INGRESO = "AMBULATORIO" (TIEMPO_FACTURACION_AMBULATORIO). Definición por confirmar; en la documentación aparece comentada.

## Visuales
- **Filtros**: Segmentadores SERVICIO, Año y Mes y botones AMBULATORIO / HOSPITALARIO (DIM_TIPO_INGRESO[TIPO_INGRESO]); botón de inicio (casa). SERVICIO excluye servicios vacíos.
- **Tarjeta**: TIEMPO PROMEDIO GESTION FACTURA, en horas.
- **Gráfico de tiempo por mes**: Titulado «TIEMPO GESTION FACTURACION»; tiempo promedio de gestión por año y mes.
- **Gráfico ambulatorio y hospitalario**: Titulado «TIEMPO FACTURACION AMBULATORIO Y HOSPITALARIO»; gráfico de área por año y mes con la medida TIEMPO_FACTURACION_HOSPITALIZACION (según el PBIP).

## Reglas de negocio
- **Filtro de página**: PERFIL = «ESCANEO FOTOCOPIAS» y ESTADO_FACTURA = «FACTURADA» (confirmado en el PBIP).
- **Primera gestión**: Para cada cuenta se toma la primera vez que el perfil la recibió y la entrega correspondiente.

## Observaciones
- **Solo serie hospitalaria**: En el PBIP el gráfico «TIEMPO FACTURACION AMBULATORIO Y HOSPITALARIO» solo tiene la medida TIEMPO_FACTURACION_HOSPITALIZACION. Por confirmar si falta la serie ambulatoria.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
