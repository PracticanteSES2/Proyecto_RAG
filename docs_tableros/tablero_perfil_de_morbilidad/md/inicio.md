---
tablero: TABLERO PERFIL DE MORBILIDAD
pagina: INICIO
nombre_funcional: Resumen de egresos por GRD, CMD y CIE10
bloque: Histórico
tablas: [MATRIZ 2024, ONCOLOGICO, Calendario]
actualizado: 2026-10-20
version: 1
---

# INICIO

## Propósito
Página principal del perfil de morbilidad: muestra el total de egresos, el promedio de edad y los pacientes atendidos por GRD, CMD y diagnóstico CIE10, con filtros por servicio, asegurador, sexo y tipo de salida. Tiene los botones hacia las demás páginas. Análisis por año y mes (bloque Histórico). Nombre de página en Power BI por confirmar.

## Fuentes de datos
- **MATRIZ 2024**: Egresos hospitalarios con diagnóstico, GRD, CMD, edad, sexo, servicio y tipo de salida.
- **ONCOLOGICO**: Marca de diagnóstico oncológico para el botón ONCOLOGICO.

## Indicadores
- **Promedio de edad**: Edad promedio en años de los pacientes egresados. Promedio de MATRIZ 2024[Edad].
- **Egresos**: Número de egresos con los filtros aplicados. Conteo de filas de MATRIZ 2024; columna contada por confirmar.
- **Pacientes atendidos**: Egresos por GRD, CMD o CIE10; mismo conteo que Egresos.

## Visuales
- **Filtros superiores**: Segmentadores de Año, Mes, Asegurador (MATRIZ 2024[Asegurador]) y Sexo.
- **Botones de servicio**: GINECO, HOSPITALIZACION, HOSPITALIZACION PARCIAL, NEONATOS, SALA AZUL, UCI/UCIN y URGENCIAS; filtran por el servicio del egreso.
- **Filtros de GRD y salida**: Segmentador de GRD y botones PUERTA y TRASLADO del tipo de salida.
- **Botón oncológico**: Deja solo los egresos con diagnóstico oncológico.
- **Tarjetas de indicadores**: Promedio de Edad y EGRESOS.
- **Barras por GRD**: Titulado «PACIENTES ATENDIDOS por GRD»; barras horizontales de mayor a menor.
- **Barras por CMD**: Titulado «PACIENTES ATENDIDOS por CMD»; barras horizontales de mayor a menor.
- **Barras por CIE10**: Titulado «PACIENTES ATENDIDOS por CIE10»; diagnósticos más frecuentes de mayor a menor.
- **Botones de navegación**: PIRAMIDE POBLACIONAL, FACTURACIÓN, PERFIL DE MORBILIDAD (abre DETALLE PERFIL DE MORBILIDAD), PERIOPERATORIA y ATENCIONES AMBULATORIAS.

## Reglas de negocio
- **Ejes de diagnóstico**: Las barras usan las columnas calculadas GRD_R, CMD_R y CIE10_R de MATRIZ 2024 (por confirmar en el PBIP del informe).
- **Botones de servicio**: Corresponden a los valores de MATRIZ 2024[SERVICIOS]; por confirmar si el visual usa SERVICIOS o Servicio_Agrupado.
- **Tipo de salida**: PUERTA y TRASLADO solo existen en egresos de 2025 en adelante; al marcarlos se excluyen los egresos de la matriz histórica.

## Observaciones
- **Filtro de día anunciado**: La documentación menciona filtros por día y por GRD en la franja superior; en la captura la franja tiene Año, Mes, Asegurador y Sexo, y el día no aplica porque la fecha del egreso es mensual.
- **Columna del botón oncológico**: Puede ser ONCOLOGICO[ONCOLOGICO], MATRIZ 2024[ONCOLOGICOM] o MATRIZ 2024[P_ONCOLOGICO]; por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP (solo modelo semántico).
