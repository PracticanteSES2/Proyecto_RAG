---
tablero: TABLERO CONTROL FACTURACION
pagina: ESTACION ENFERMERIA
nombre_funcional: Tiempo de gestión en estación de enfermería
bloque: Histórico
tablas: [FACTURACION PERFILES, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# ESTACION ENFERMERIA

## Propósito
Muestra cuánto tardan las cuentas en el perfil ESTACION DE ENFERMERIA, es decir en la estación de enfermería (primera entrega de la cuenta después del egreso): tiempo promedio, evolución por año y mes y comparación entre ingresos ambulatorios y hospitalarios. Análisis histórico; se llega desde el botón ESTACION DE ENFERMERIA de RESUMEN FACTURACION.

## Fuentes de datos
- **FACTURACION PERFILES**: Gestiones por cuenta y perfil (ver RESUMEN FACTURACION); esta página solo muestra el perfil ESTACION DE ENFERMERIA (código 1) de cuentas con factura emitida. Egresos desde el 1 de agosto de 2025.

## Indicadores
- **Tiempo promedio de gestión de factura**: Promedio en horas de 'FACTURACION PERFILES'[TIEMPO], es decir de las horas entre que el perfil recibe la cuenta y la entrega. Agregación: promedio de la columna.
- **Tiempo hospitalario**: Medida TIEMPO_FACTURACION_HOSPITALIZACION = CALCULATE(AVERAGE('FACTURACION PERFILES'[TIEMPO]), 'FACTURACION PERFILES'[TIPO INGRESO] = "HOSPITALARIO"). Unidad: horas.
- **Tiempo ambulatorio**: Promedio de TIEMPO para TIPO INGRESO = "AMBULATORIO" (TIEMPO_FACTURACION_AMBULATORIO). Definición por confirmar; en la documentación aparece comentada.

## Visuales
- **Filtros**: Segmentadores SERVICIO, Año y Mes; botón de inicio (casa). SERVICIO excluye servicios vacíos.
- **Tarjeta**: TIEMPO PROMEDIO GESTION FACTURA, en horas.
- **Gráfico de tiempo por mes**: Titulado «TIEMPO GESTION FACTURACION»; tiempo promedio de gestión por año y mes.
- **Gráfico ambulatorio y hospitalario**: Titulado «TIEMPO FACTURACION AMBULATORIO Y HOSPITALARIO»; líneas TIEMPO AMBULATORIO y TIEMPO HOSPITALARIO por año y mes.

## Reglas de negocio
- **Filtro de página**: PERFIL = «ESTACION DE ENFERMERIA» y ESTADO_FACTURA = «FACTURADA» (confirmado en el PBIP).
- **Primera gestión**: Para cada cuenta se toma la primera vez que el perfil la recibió y la entrega correspondiente.

## Observaciones
- **Sin datos en la captura**: En la captura de la documentación la tarjeta aparece «(En blanco)» y los gráficos vacíos. Por confirmar si el perfil registra entregas con factura emitida.
- **Gráfico repetido en la documentación**: La documentación describe dos veces «Tiempo gestión facturación»; el segundo gráfico es el de ambulatorio y hospitalario.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
