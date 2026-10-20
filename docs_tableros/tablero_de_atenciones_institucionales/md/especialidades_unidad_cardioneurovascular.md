---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: ESPECIALIDADES UNIDAD CARDIONEUROVASCULAR
nombre_funcional: Atenciones de la Unidad Cardioneurovascular por especialidad y servicio
bloque: Histórico
tablas: [UNIDAD_CARDIOVASCULAR, Calendario]
actualizado: 2026-10-20
version: 1
---

# ESPECIALIDADES UNIDAD CARDIONEUROVASCULAR

## Propósito
Muestra cómo se reparten las atenciones de la Unidad Cardioneurovascular entre especialidades (hemodinamia, cirugía vascular, electrofisiología, etc.) y cuáles servicios se hacen con más frecuencia. Se llega desde el botón ESPECIALIDAD de UNIDAD CARDIONEUROVASCULAR y se vuelve con la flecha.

## Fuentes de datos
- **UNIDAD_CARDIOVASCULAR**: Servicios del área 108 desde 2024-01-01 con su CUPS, descripción del servicio y especialidad agrupada; misma tabla de la página UNIDAD CARDIONEUROVASCULAR.

## Indicadores
- **Cantidad de atenciones**: Suma de CANTIDAD del año seleccionado o del año anterior cerrado. Medida CANT_ATENCIONESUCAR.
- **Promedio de atenciones**: Registros del año divididos por 12. Medida PROM_ATENCIONESUCAR.

## Visuales
- **Segmentadores**: ASEGURADOR, Año, Mes y TIPO INGRESO.
- **Mapa de árbol por especialidad**: Treemap «CANTIDAD ATENCIONES POR ESPECIALIDAD» con las atenciones de cada especialidad agrupada.
- **Tarjetas de atenciones**: «CANTIDAD ATENCIONES» y una tarjeta con el promedio rotulada con el nombre técnico «PROM_ATENCIONESUCAR».
- **Gráfico de distribución de servicios**: Barras «DISTRIBUCION DE SERVICIOS DE LA UNIDAD CARDIOVASCULAR» con la cantidad de cada servicio (descripción del CUPS), de mayor a menor.
- **Botón de regreso**: Flecha que vuelve a UNIDAD CARDIONEUROVASCULAR.

## Reglas de negocio
- **Especialidad por CUPS**: La especialidad se asigna por listas de códigos CUPS: Cirugía Vascular, Cirugía Cardiovascular, Electrofisiología, Hemodinamia, Neurointervencionismo, Procedimiento de Imágenes y Radiología intervencionista; los demás códigos quedan como OTRO.

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar; la documentación la titula «TABLERO DE ESPECIALIDADES UNIDAD CARDIONEUROVASCULAR».
- **Rótulos distintos a la consulta**: El treemap muestra «Cx vascular» mientras la consulta documentada asigna «Cirugía Vascular»; la consulta puede estar desactualizada.
- **Código CUPS sospechoso**: La lista de Radiología intervencionista incluye '3720102', de 7 dígitos; los CUPS tienen 6. Por confirmar.
- **Tarjeta con nombre técnico**: La tarjeta de promedio muestra el nombre de la medida en lugar de un rótulo para el usuario.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
