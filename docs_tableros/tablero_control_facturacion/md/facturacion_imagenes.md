---
tablero: TABLERO CONTROL FACTURACION
pagina: FACTURACION IMAGENES
nombre_funcional: Tiempo de gestión en facturación de imágenes
bloque: Histórico
tablas: [FACTURACION PERFILES, CALENDARIO]
actualizado: 2026-10-28
version: 2
---

# FACTURACION IMAGENES

## Propósito
Muestra cuánto tardan las cuentas en el perfil FACTURACION IMAGENES, es decir en la facturación de imágenes diagnósticas: tiempo promedio, evolución por año y mes y comparación entre ingresos ambulatorios y hospitalarios. Análisis histórico; se llega desde el botón FACTURACION IMAGENES de RESUMEN FACTURACION. Página oculta en Power BI; se llega por botón.

## Fuentes de datos
- **FACTURACION PERFILES**: Gestiones por cuenta y perfil (ver RESUMEN FACTURACION); esta página solo muestra el perfil FACTURACION IMAGENES (código 21) de cuentas con factura emitida. Egresos desde el 1 de agosto de 2025.

## Indicadores
- **Tiempo promedio de gestión de factura**: Promedio en horas de 'FACTURACION PERFILES'[TIEMPO], es decir de las horas entre que el perfil recibe la cuenta y la entrega. Agregación: promedio de la columna.
- **Tiempo hospitalario**: Medida TIEMPO_FACTURACION_HOSPITALIZACION = CALCULATE(AVERAGE('FACTURACION PERFILES'[TIEMPO]), 'FACTURACION PERFILES'[TIPO INGRESO] = "HOSPITALARIO"). Unidad: horas.
- **Tiempo ambulatorio**: Medida TIEMPO_FACTURACION_AMBULATORIO: promedio de TIEMPO de las cuentas con TIPO INGRESO = AMBULATORIO. Unidad: horas.

## Visuales
- **Filtros**: Segmentadores «SERVICIO» (FACTURACION PERFILES[SERVICIO]), «Date Año» y «Date Mes» (CALENDARIO[Date]) y «TIPO_INGRESO» (DIM_TIPO_INGRESO[TIPO_INGRESO], botones AMBULATORIO / HOSPITALARIO); botón de inicio (casa) que vuelve a INICIO.
- **Tarjeta**: TIEMPO PROMEDIO GESTION FACTURA: promedio de 'FACTURACION PERFILES'[TIEMPO], en horas.
- **Gráfico de tiempo por mes**: Titulado «TIEMPO GESTION FACTURACION»; tiempo promedio de gestión por año y mes.
- **Gráfico ambulatorio y hospitalario**: Gráfico de áreas titulado «TIEMPO FACTURACION AMBULATORIO Y HOSPITALARIO»; en esta página solo tiene la serie TIEMPO HOSPITALARIO por año y mes.
- **Botón PROCESO FACTURACION**: Botón que lleva a la página EN PROCESO FACTURACION DE IMAGENES, con las cuentas de este perfil que siguen sin entregarse.

## Reglas de negocio
- **Filtro de página**: PERFIL = «FACTURACION IMAGENES» y ESTADO_FACTURA = «FACTURADA» (confirmado en el PBIP): solo cuentas con factura vigente.
- **Primera gestión**: Para cada cuenta se toma la primera vez que el perfil la recibió y la entrega correspondiente.

## Observaciones
- **Página EN PROCESO relacionada**: Las cuentas de este perfil que siguen abiertas se ven en EN PROCESO FACTURACION IMAGENES.
- **Solo serie hospitalaria**: El gráfico de ambulatorio y hospitalario de esta página solo trae la serie TIEMPO HOSPITALARIO, a pesar de su título (confirmado en el PBIP)
- **Horas por día**: FACTURACION PERFILES convierte FECHA_RECIBE y FECHA_ENTREGA a fecha sin hora, por lo que el tiempo de gestión en horas es siempre un múltiplo de 24 (equivale a días por 24)

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
