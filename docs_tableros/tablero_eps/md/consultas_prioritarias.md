---
tablero: TABLERO EPS
pagina: CONSULTAS PRIORITARIAS
nombre_funcional: Detalle de consultas prioritarias por estado
bloque: Histórico
tablas: [CONSULTAS_PRIORITARIAS]
actualizado: 2026-10-20
version: 1
---

# CONSULTAS PRIORITARIAS

## Propósito
Detalle de las consultas prioritarias de urgencias (pacientes de triage 4 y 5): listado de pacientes con su aseguradora y distribución de las citas por estado. Es histórica (desde 2022). Se llega con el botón DETALLE CONSULTAS PRIORITARIAS de la página principal.

## Fuentes de datos
- **Consulta de consultas prioritarias**: Citas de CITAS_MEDICAS desde el 2022-01-01 hasta hoy cuya actividad (CMANOMBRE) contiene «PRIORITARIA», con fecha de la cita, aseguradora, estado y grupo de edad.

## Indicadores
- **Consultas prioritarias**: Cantidad de citas prioritarias. Unidad: consultas. Cálculo por confirmar; el catálogo local sugiere COUNTROWS('CONSULTAS_PRIORITARIAS') como medida inferida.
- **Participación por estado**: Porcentaje de citas en cada estado sobre el total filtrado. Unidad: porcentaje.

## Visuales
- **Filtros de segmentación**: Listas de Año, Mes, Día, ASEGURADORA y ESTADO CONSULTA.
- **Tabla detalle de pacientes**: Columnas DOCUMENTO PACIENTE, NOMBRE PACIENTE y ASEGURADORA, una fila por cita.
- **Gráfico consultas por estado**: Torta titulada «CONSULTAS por ESTADO» con cantidad y porcentaje de CONFIRMADO, ANULADO y REGISTRADO.
- **Botón VOLVER**: Regresa a la página principal.

## Reglas de negocio
- **Estados de la cita**: CCMESTADO 0 es REGISTRADO, 1 es ANULADO y 2 es CONFIRMADO.
- **Todas las citas entran**: El filtro de solo confirmadas está desactivado en la consulta; se cargan registradas, anuladas y confirmadas.
- **Documentos excluidos**: Se excluyen las citas con documento de paciente 30, 31, 32, 33, 34, 35, 36, 37, 38 o 39.
- **Grupo de edad**: «MENORES DE EDAD» si la diferencia de años entre la fecha de nacimiento y la fecha de la cita es menor que 18.
- **Agrupación de aseguradoras**: NUEVA EPS, SURA, SANITAS y MALLAMAS se agrupan igual que en el resto del tablero (ver General).

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Documentos 30 a 39**: Por confirmar el motivo de la exclusión; parecen documentos de prueba o genéricos.
- **Edad aproximada**: DATEDIFF por años cuenta cambios de año calendario, no años cumplidos; un paciente puede quedar como mayor de edad meses antes de cumplir 18.
- **Uniones que pueden excluir citas**: La consulta exige municipio, departamento, médico y especialidad (INNER JOIN); citas sin alguno de esos datos no aparecen. Por confirmar si es intencional.
- **Relación con la tarjeta principal**: En la captura, la cantidad de CONFIRMADO coincide con la tarjeta de consultas prioritarias de la página principal.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
