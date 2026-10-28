---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: Página 1
nombre_funcional: Página de trabajo de urgencias (por confirmar)
bloque: Histórico
tablas: [DIM_SERVICIO]
actualizado: 2026-10-28
version: 2
---

# Página 1

## Propósito
Página visible del informe, sin visuales en el PBIP ni documentación propia. Su filtro deja solo los servicios de urgencias (URGENCIAS, URGENCIAS 2 PISO, URGENCIAS 2 SUR, URGENCIAS EXPANSION, URGENCIAS SALA AZUL y BOTON AZUL 3 PISO) de DIM_SERVICIO[SERVICIO_HOMOLOGADO]. Parece una página de trabajo; por confirmar.

## Reglas de negocio
- **Filtro de página**: DIM_SERVICIO[SERVICIO_HOMOLOGADO] en ('URGENCIAS', 'URGENCIAS 2 PISO', 'URGENCIAS 2 SUR', 'URGENCIAS EXPANSION', 'URGENCIAS SALA AZUL', 'BOTON AZUL 3 PISO')

## Observaciones
- **Bloque deducido**: Se asignó el bloque Histórico según el nombre de la página. Por confirmar.
- **Sin documentación**: El PBIP trae la página sin visuales y no hay documento del propietario; qué muestra se debe confirmar con el dueño del tablero.

## Historial de cambios
- **2026-10-28 · v1**: Borrador generado automáticamente a partir del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
