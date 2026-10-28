---
tablero: BRIEFING HOSPITALARIO
pagina: REPS
nombre_funcional: Capacidad instalada habilitada según el REPS
bloque: Día
tablas: [REPS]
actualizado: 2026-10-28
version: 2
---

# REPS

## Propósito
Muestra la capacidad instalada habilitada del hospital según el Registro Especial de Prestadores de Servicios de Salud (REPS): camas, camillas, consultorios, salas y sillas por grupo, y su participación en el total. Es una foto de la capacidad vigente, no una serie en el tiempo. Se llega desde el botón DETALLE de la tarjeta REPS en INICIO.

## Fuentes de datos
- **REPS**: Archivo Excel «ESTADO ACTUAL NOVEDADES REPS SES 2025.xlsx» en el SharePoint de seguridad del paciente, con GRUPO CAPACIDAD Y CONCEPTO y CAPACIDAD INSTALADA REPS.

## Indicadores
- **Capacidad instalada REPS**: Número de recursos habilitados (camas, camillas, consultorios, salas o sillas). Suma de REPS[CAPACIDAD INSTALADA REPS].
- **Participación por grupo**: Porcentaje de cada grupo sobre la capacidad total.

## Visuales
- **Tabla de capacidad**: GRUPO CAPACIDAD Y CONCEPTO y CAPACIDAD INSTALADA REPS, con fila de total.
- **Participación por grupo**: Barras horizontales con el porcentaje de cada grupo, de mayor a menor.
- **Tarjeta REPS en INICIO**: Muestra el total de la capacidad instalada.

## Reglas de negocio
- **Grupos de capacidad**: Incluye camas (por ejemplo hospitalización general adultos, cuidado intensivo e intermedio adultos y neonatal, atención del parto), camillas de observación, consultorios de consulta externa y urgencias, salas de parto, procedimiento y quirófano, y sillas.

## Observaciones
- **Visual ajeno en la documentación**: La documentación de REPS incluye una sección «Tabla Detalle Medicamentos Desabastecidos» copiada de otra página; no pertenece a REPS.
- **Actualización manual**: Los datos dependen de que se actualice el Excel en SharePoint; el nombre del archivo dice 2025. Por confirmar si se mantiene al día.
- **Relación con GESTIÓN CAMAS**: La tarjeta CAPACIDAD INSTALADA REPS de GESTIÓN CAMAS usa esta tabla filtrada a los grupos de camas del área. Por confirmar.
- **Nombre de página**: La página se llama REPS en Power BI; está oculta y se llega con el botón DETALLE de su visual en INICIO.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
