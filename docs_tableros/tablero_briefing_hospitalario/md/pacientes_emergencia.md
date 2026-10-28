---
tablero: BRIEFING HOSPITALARIO
pagina: PACIENTES EMERGENCIA
nombre_funcional: Pacientes atendidos por el movimiento telúrico de agosto de 2026 en Manizales
bloque: Histórico
tablas: []
actualizado: 2026-10-28
version: 2
---

# PACIENTES EMERGENCIA

## Propósito
Registro de los pacientes atendidos por el hospital durante el movimiento telúrico de Manizales y los días siguientes: total de pacientes, edad promedio, distribución por observación, rango de edad y EPS. Es un registro de un evento puntual, no un indicador diario. Se llega desde el botón DETALLE del visual PACIENTES EMERGENCIA MOVIMIENTO TELURICO en INICIO.

## Fuentes de datos
- **Archivo de emergencia**: Excel «DATOS DE PACIENTES - EMEREGENCIA HOJA DE TRABAJO (1).xlsx» en el SharePoint de coordinación de facturación hospitalaria, con documento, edad, aseguradora, fecha y observación de cada paciente. Nombre de la tabla en el modelo por confirmar.

## Indicadores
- **Total de pacientes**: Pacientes atendidos por la emergencia. Recuento de PACIENTES EMERGENCIA[DOCUMENTO].
- **Promedio de edad**: Edad promedio de los pacientes, en años. Promedio de PACIENTES EMERGENCIA[EDAD].

## Visuales
- **Tarjetas**: TOTAL DE PACIENTES y PROMEDIO EDAD.
- **Segmentador ASEGURADOR**: Filtra por EPS del paciente.
- **Pacientes por observación**: Columnas por fecha con el recuento de documentos por OBSERVACION: ADRES, DERIVADO A CONSULTA PRIORITARIA, EPS y FALLECIDO.
- **Pacientes por rango de edad**: Columnas por fecha con el recuento por RANGO_EDAD: DE 0 A 17 AÑOS, DE 18 A 65 AÑOS y MAYORES DE 65 AÑOS.
- **Pacientes por EPS**: Mapa de árbol con la cantidad de pacientes por EPS.
- **Visual en INICIO**: Torta con pacientes por OBSERVACION y tarjeta TOTAL DE PACIENTES.

## Reglas de negocio
- **Fechas del evento**: Las atenciones registradas son del 10, 11 y 14 de agosto de 2026.

## Observaciones
- **Límite de 65 años**: Un paciente de 65 años cae en «DE 18 A 65 AÑOS»; «MAYORES DE 65 AÑOS» empieza en 66 (RANGO_EDAD); sin edad queda «NO REGISTRA EDAD».
- **Significado de las observaciones**: La interpretación de EPS y ADRES como responsable del pago está por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
