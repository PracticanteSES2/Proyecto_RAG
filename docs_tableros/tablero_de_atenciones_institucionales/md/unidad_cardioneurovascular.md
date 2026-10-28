---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: UNIDAD CARDIONEUROVASCULAR
nombre_funcional: Atenciones mensuales de la Unidad Cardioneurovascular
bloque: Histórico
tablas: [UNIDAD_CARDIOVASCULAR, Calendario, MostrarProyeccion]
actualizado: 2026-10-20
version: 1
---

# UNIDAD CARDIONEUROVASCULAR

## Propósito
Muestra la cantidad mensual de atenciones de la Unidad Cardioneurovascular, compara los años con proyección opcional y las reparte por asegurador. Desde el botón ESPECIALIDAD se llega a ESPECIALIDADES UNIDAD CARDIONEUROVASCULAR.

## Fuentes de datos
- **UNIDAD_CARDIOVASCULAR**: Servicios prestados en el área de servicio con código 108 desde 2024-01-01: ingreso, fecha del servicio, cantidad, asegurador, CUPS y su descripción, tipo de ingreso, médico, especialidad agrupada y asegurador agrupado (AGRUPA).

## Indicadores
- **Atenciones**: Suma de cantidades de servicios. Cálculo: ATENCIONES = SUM('UNIDAD_CARDIOVASCULAR'[CANTIDAD]); ATE2024, ATE2025 y ATE2026 la fijan a cada año.
- **Cantidad de atenciones**: Suma de CANTIDAD del año seleccionado o, si no hay año, del año anterior cerrado. Medida CANT_ATENCIONESUCAR.
- **Promedio de atenciones**: Número de registros (COUNT de INGRESO) dividido por 12, del año anterior cerrado si no hay filtro de tiempo o de cada año seleccionado (sumando los años). Medida PROM_ATENCIONESUCAR.
- **Proyección de atenciones**: Atenciones del mismo mes del año anterior por (1 + crecimiento frente al mismo mes de hace dos años); solo con «Mostrar proyección» = SI. Medida PROYECCION_ATEN.

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes y TIPO DE INGRESO.
- **Casilla Mostrar proyección**: Casilla «SI» que muestra u oculta la línea de proyección.
- **Gráfico de atenciones por mes**: Líneas «CANTIDAD MENSUAL DE ATENCIONES UNIDAD CARDIONEUROVASCULAR», una línea por año y una PROYECCION.
- **Tabla de atenciones por asegurador**: ASEGURADOR (agrupado) y CANTIDAD ATENCIONES, con total.
- **Tabla de detalle**: Matriz de atenciones por año (filas) y mes (columnas) con totales.
- **Tarjetas de atenciones**: «PROMEDIO ATENCIONES» y «CANTIDAD ATENCIONES».
- **Botón Especialidad**: Lleva a ESPECIALIDADES UNIDAD CARDIONEUROVASCULAR; el botón de casa vuelve a INICIO.

## Reglas de negocio
- **Tipo de ingreso**: AMBULATORIO cuando el ingreso es de tipo 1; si no, HOSPITALARIO.
- **Exclusiones**: Se excluyen ingresos en estado 2 o 4 y órdenes de servicio en estado 2.
- **Asegurador agrupado**: NUEVA_EPS, EPS_SURA, FOMAG (fiduciaria La Previsora), SALUD TOTAL, DTSC (dirección territorial), EPS SANITAS, UNISALUD (Universidad Nacional) y ASEGURADORAS Y MP (seguros, Colmédica, Colsanitas, Medplus y Medisanitas); el resto queda en OTRAS.
- **Año por defecto**: Sin año seleccionado, las tarjetas muestran el año anterior al año en curso.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar. La documentación la titula «UNIDAD CARDIOVASCULAR» y el gráfico «UNIDAD CARDIONEUROVASCULAR».
- **Proyección con años fijos**: PROYECCION_ATEN usa ATE2025 y ATE2024, que fijan el año dentro de la fórmula; la proyección siempre compara 2025 contra 2024, sin importar el año visto.
- **Pacientes sin teléfono principal**: La consulta une con los teléfonos del paciente exigiendo teléfono principal; los servicios de pacientes sin teléfono principal quedan fuera.
- **Bases distintas**: CANTIDAD ATENCIONES suma CANTIDAD y PROMEDIO ATENCIONES cuenta registros; el promedio por 12 no es la cantidad dividida por 12.
- **Medida del gráfico**: La documentación dice que el gráfico usa PROM_ATENCIONESUCAR, pero sus valores coinciden con la cantidad mensual. Por confirmar.
- **Versiones distintas de medidas**: PROM_ATENCIONESUCAR del modelo es más simple que la documentada y PROM_GENERALUCAR está vacía en la documentación. Por confirmar cuál está vigente.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
