---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: ATENCIONES PEDIÁTRICAS CONSULTAS
nombre_funcional: Consultas pediátricas de urgencias por mes y clasificación
bloque: Histórico
tablas: [CONSULTA_URGENCIAS, Calendario]
actualizado: 2026-10-28
version: 2
---

# ATENCIONES PEDIÁTRICAS CONSULTAS

## Propósito
Muestra cuántas consultas pediátricas de urgencias se atienden cada mes, compara los años y muestra su distribución por clasificación de triage. Desde qué botón se llega: por confirmar (tiene flecha de regreso).

## Fuentes de datos
- **CONSULTA_URGENCIAS**: La misma tabla de la página URGENCIAS (consultas médicas de urgencias con triage, clasificación, grupo de edad y aseguradora).

## Indicadores
- **Consultas pediátricas por mes**: Número de consultas de menores de edad por mes. Medida por confirmar.
- **Consultas del año en curso**: Cálculo documentado: PRIORITARIAS_2025 = CALCULATE(COUNT(CONSULTA_URGENCIAS[OID_TRIAGE]), YEAR(CONSULTA_URGENCIAS[FECHA_FOLIO]) = YEAR(TODAY())).
- **Consultas de PRIORITARIAS_2024**: Cálculo documentado: CALCULATE(COUNT(CONSULTA_URGENCIAS[OID_TRIAGE]), YEAR(CONSULTA_URGENCIAS[FECHA_FOLIO]) = YEAR(TODAY()-1)); también da el año en curso.

## Visuales
- **Segmentadores**: ASEGURADOR, Año y Mes.
- **Gráfico de consultas por mes**: Líneas «CONSULTAS PEDIATRICAS POR MES», una línea por año.
- **Gráfico por clasificación**: Torta «CONSULTAS PEDIATRICAS por CLASIFICACIÓN TRIAGE» con la proporción de los códigos I, II, III y IV.
- **Tabla de detalle anual**: Matriz de consultas por año (filas) y mes (columnas).
- **Botón de regreso**: Flecha que vuelve a la página anterior.

## Reglas de negocio
- **Consulta pediátrica**: Consulta de urgencias de un paciente menor de 18 años (MENORES_EDAD = MENORES). Filtro exacto de la página por confirmar.
- **Clasificación**: Se agrupa igual que en TRIAGE (IIIU en III; IIP e IIS en II; UA excluido).

## Observaciones
- **Nombre de página**: El PBIP actual no trae una página con este nombre; la página existe en la documentación del propietario («ATENCIONES PEDIÁTRICAS – CONSULTAS»). Por confirmar su nombre en Power BI.
- **Gráfico vacío**: En la captura el gráfico de líneas aparece sin datos.
- **Medidas desactualizadas**: Las medidas documentadas cuentan OID_TRIAGE, columna que ya no existe en CONSULTA_URGENCIAS, y su nombre (PRIORITARIAS) no corresponde a consultas pediátricas.
- **Consulta desactualizada**: La consulta documentada es la anterior de urgencias (desde 2023); el modelo actual carga desde 2025-01-01 y excluye la causa de ingreso 4 (enfermedad general pediatría). Por confirmar cómo afecta a esta página.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
