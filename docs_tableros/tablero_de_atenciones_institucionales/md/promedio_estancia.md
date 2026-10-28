---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: PROMEDIO ESTANCIA
nombre_funcional: Promedio de estancia por egreso (por confirmar)
bloque: Histórico
tablas: [PROMEDIO_ESTANCIA, CAMAS, Calendario]
actualizado: 2026-10-28
version: 2
---

# PROMEDIO ESTANCIA

## Propósito
Página oculta del informe sin visuales en el PBIP ni documentación propia. Su filtro excluye los egresos con TIPO_SALIDA vacío o TRASLADO. La tabla PROMEDIO_ESTANCIA trae los días de hospitalización por egreso y sus medidas son [PROM_ESTANCIA], [GIRO_CAMA], [EGRESOS_2024] y [EGRESOS_2025]. Visuales por confirmar.

## Reglas de negocio
- **Filtro de página**: PROMEDIO_ESTANCIA[TIPO_SALIDA] no en (vacío, 'TRASLADO')

## Observaciones
- **Bloque deducido**: Se asignó el bloque Histórico según el nombre de la página. Por confirmar.
- **Sin documentación**: El PBIP trae la página sin visuales y no hay documento del propietario; qué muestra se debe confirmar con el dueño del tablero.

## Historial de cambios
- **2026-10-28 · v1**: Borrador generado automáticamente a partir del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
