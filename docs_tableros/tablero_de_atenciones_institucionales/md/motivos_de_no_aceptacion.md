---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: MOTIVOS DE NO ACEPTACIÓN
nombre_funcional: Causas de no aceptación de solicitudes de referencia
bloque: Histórico
tablas: [REFERENCIA, ASEGURADORAS]
actualizado: 2026-10-20
version: 1
---

# MOTIVOS DE NO ACEPTACIÓN

## Propósito
Muestra por qué no se aceptan las solicitudes de referencia: cantidad y proporción por causa, su evolución mensual y su distribución por servicio. Se llega con el botón MOTIVOS NO ACEPTACIÓN de REFERENCIA Y CONTRARREFERENCIA.

## Fuentes de datos
- **REFERENCIA**: La misma tabla de REFERENCIA Y CONTRARREFERENCIA; la causa sale de NOMBRE_CAUSA (catálogo DIM_CAUSAS).

## Indicadores
- **Solicitudes por causa**: Número de solicitudes por causa de no aceptación, mes y año. Medida o columna contada por confirmar.
- **Distribución por causa**: Porcentaje de cada causa sobre el total de solicitudes con causa.

## Visuales
- **Segmentadores**: CAUSA, ASEGURADORA, Año y Mes.
- **Gráfico de barras por causa**: Columnas «SOLICITUDES por CAUSA» ordenadas de mayor a menor, en miles.
- **Gráfico circular por causa**: Torta «SOLICITUDES por CAUSA» con la cantidad y el porcentaje de cada causa.
- **Tabla de detalle anual**: Matriz con año y, debajo, cada causa en filas, meses en columnas y totales.
- **Tabla por servicio**: Tabla SERVICIO y CANTIDAD con las solicitudes por servicio del hospital.
- **Botón de regreso**: Flecha que vuelve a REFERENCIA Y CONTRARREFERENCIA.

## Reglas de negocio
- **Causas registradas**: Aceptado por otra institución, Supera la capacidad instalada, No disponibilidad de cama, No especialidad, No contratación, Es de menor complejidad, Menor de edad, No disponibilidad de equipos y NO HABILITADO (según la captura).

## Observaciones
- **Nombre de página**: Nombre de página en Power BI por confirmar.
- **Tabla por servicio sin relación**: En la captura todos los servicios muestran la misma cantidad (el total general), así que la tabla de servicios no está relacionada con las solicitudes. Tabla de origen por confirmar.
- **Causa mayoritaria**: «Aceptado por otra institución» es la causa más frecuente; por confirmar si debe tratarse como motivo de no aceptación.
- **Totales distintos al estado No Aceptado**: El total de solicitudes con causa no coincide con el de solicitudes No Aceptado de la página principal. Por confirmar el filtro de la página.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
