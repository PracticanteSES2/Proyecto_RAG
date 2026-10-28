---
tablero: TABLERO CONTROL FACTURACION
pagina: AUDITORES EXTERNOS
nombre_funcional: Tiempo de gestión en auditores externos
bloque: Histórico
tablas: [FACTURACION PERFILES, CALENDARIO]
actualizado: 2026-10-28
version: 2
---

# AUDITORES EXTERNOS

## Propósito
Muestra cuánto tardan las cuentas en el perfil AUDITORES EXTERNOS, es decir en la revisión por auditores externos: tiempo promedio, evolución por año y mes y comparación entre ingresos ambulatorios y hospitalarios. Análisis histórico; se llega desde el botón AUDITORES EXTERNOS de RESUMEN FACTURACION. Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **FACTURACION PERFILES**: Gestiones por cuenta y perfil (ver RESUMEN FACTURACION); esta página solo muestra el perfil AUDITORES EXTERNOS (código 15) de cuentas con factura emitida. Egresos desde el 1 de agosto de 2025.

## Indicadores
- **Tiempo promedio de gestión de factura**: Promedio en horas de 'FACTURACION PERFILES'[TIEMPO], es decir de las horas entre que el perfil recibe la cuenta y la entrega. Agregación: promedio de la columna.
- **Tiempo hospitalario**: Medida TIEMPO_FACTURACION_HOSPITALIZACION = CALCULATE(AVERAGE('FACTURACION PERFILES'[TIEMPO]), 'FACTURACION PERFILES'[TIPO INGRESO] = "HOSPITALARIO"). Unidad: horas.
- **Tiempo ambulatorio**: Medida TIEMPO_FACTURACION_AMBULATORIO: promedio de TIEMPO de las cuentas con TIPO INGRESO = AMBULATORIO. Unidad: horas.

## Visuales
- **Filtros**: Segmentadores SERVICIO, Año y Mes; botón de inicio (casa).
- **Tarjeta**: TIEMPO PROMEDIO GESTION FACTURA, en horas.
- **Gráfico de tiempo por mes**: Titulado «TIEMPO GESTION FACTURACION»; tiempo promedio de gestión por año y mes.
- **Gráfico ambulatorio y hospitalario**: Titulado «TIEMPO FACTURACION AMBULATORIO Y HOSPITALARIO»; líneas TIEMPO AMBULATORIO y TIEMPO HOSPITALARIO por año y mes.

## Reglas de negocio
- **Filtro de página**: PERFIL = «AUDITORES EXTERNOS» y ESTADO_FACTURA = «FACTURADA». Por confirmar en esta página; es el patrón de las páginas de perfil que trae el PBIP.
- **Primera gestión**: Para cada cuenta se toma la primera vez que el perfil la recibió y la entrega correspondiente.

## Observaciones
- **Sin datos en la captura**: En la captura de la documentación la tarjeta aparece «(En blanco)» y los gráficos vacíos. Por confirmar si el perfil tiene registros.
- **Sin página en el PBIP**: El PBIP local no trae esta página: el botón AUDITORES EXTERNOS de RESUMEN FACTURACION no tiene destino configurado. Describe la documentación del propietario.
- **Horas por día**: FACTURACION PERFILES convierte FECHA_RECIBE y FECHA_ENTREGA a fecha sin hora, por lo que el tiempo de gestión en horas es siempre un múltiplo de 24 (equivale a días por 24)

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
