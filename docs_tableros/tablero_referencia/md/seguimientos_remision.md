---
tablero: TABLERO REFERENCIA
pagina: SEGUIMIENTOS REMISION
nombre_funcional: Bitácora de seguimiento de las remisiones
bloque: Histórico
tablas: [DETALLE_REMISIONES, CONTRARREFERENCIA]
actualizado: 2026-10-28
version: 1
---

# SEGUIMIENTOS REMISION

## Propósito
Página del informe con la bitácora de seguimiento de las remisiones del hospital a otras instituciones: las anotaciones registradas por los usuarios sobre cada remisión. Es el equivalente, para remisiones, de DETALLE_RECEPCIONES. Análisis histórico desde 2023. Por confirmar los visuales de la página, porque el PBIP local no los incluye y la documentación del propietario describe una sola página de remisión (ver DETALLE REMISION).

## Fuentes de datos
- **DETALLE_REMISIONES**: Anotaciones de seguimiento de cada remisión (HISTORICO_REMISIONES_DW) con fecha de registro entre el 1 de enero de 2023 y hoy; incluye descripción, alerta, verificación y usuario que registra.
- **CONTRARREFERENCIA**: Datos de la remisión a la que se asocia cada anotación, por OidRemision.

## Reglas de negocio
- **Nombre del usuario**: DETALLE_REMISIONES[NOMBRE_COMPLETO] une USU_NOMBRES y USU_APELLIDOS con un espacio.

## Observaciones
- **Visuales sin documentar**: No hay visuales documentados para esta página. Por confirmar.
- **Texto libre clínico**: Las descripciones son texto libre y pueden contener información clínica; la página debe tratarse como información sensible.

## Historial de cambios
- **2026-10-28 · v1**: Diccionario y revisión contra el modelo y el informe.
