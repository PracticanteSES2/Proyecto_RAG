---
tablero: TABLERO NAOS
pagina: LISTADO
nombre_funcional: Listado de pacientes con pendientes activos
bloque: Día
tablas: [PACIENTES]
actualizado: 2026-11-03
version: 4
---

# LISTADO

## Propósito
Página principal del tablero NAOS. Muestra en tiempo real los pacientes hospitalizados con pendientes activos, con colores que priorizan por días de estancia y tipo de pendiente, y su distribución por servicio y por clasificación. Desde aquí se navega a exámenes pendientes, trámites de gestión clínica y cirugías pendientes.

## Fuentes de datos
- **PACIENTES**: Vista TABLERO_NAOS cargada completa; un registro por paciente con servicio, cama, aseguradora, clasificación, días de estancia y marcas de solicitud de cama, dieta y gestión clínica pendientes.

## Indicadores
- **Total de pacientes**: Cantidad de pacientes con pendientes activos según los filtros. Unidad: pacientes. Se cuenta PACIENTES[AINCONSEC] en la tarjeta; el modelo no tiene medidas.
- **Pacientes por servicio**: Cantidad y porcentaje de pacientes por servicio hospitalario (PACIENTES[SERVICIO]). Unidad: pacientes y porcentaje.
- **Pacientes por clasificación**: Cantidad y porcentaje de pacientes por clasificación de aseguramiento (gráfico «CLASIFICACIÓN», que agrupa por PACIENTES[TIPO_PACIENTE] y cuenta PACIENTES[ADNINGRESO]). Unidad: pacientes y porcentaje.

## Visuales
- **Tarjeta total de pacientes**: Número de pacientes con el rótulo PACIENTES.
- **Convenciones de colores**: Leyendas de estancia (6 a 8 Días, Entre 9 y 14 Días, 15 Días o más) y de pendientes (Dieta Pendiente, Solicitud Gestión Clínica Pendiente, Solicitud de Cama Pendiente).
- **Filtros de segmentación**: Listas de SERVICIO y TIPO PACIENTE.
- **Botones de navegación**: EXÁMENES PENDIENTES, TRÁMITES GESTIÓN CLÍNICA y CIRUGÍAS PENDIENTES llevan a las páginas de detalle.
- **Tabla detalle de pacientes**: Columnas PACIENTE, EDAD, DOCUMENTO, INGRESO, SERVICIO, CAMA, EPS, familiar o acompañante y otras más a la derecha; cada fila se pinta con ColorFila.
- **Gráfico pacientes por servicio**: Torta titulada «PACIENTES por SERVICIO» con cantidad y porcentaje por servicio (pisos, cuidado intermedio, atención domiciliaria, entre otros).
- **Gráfico pacientes por clasificación**: Torta titulada «PACIENTES por CLASIFICACIÓN» con MEDICINA PREPAGADA, PLAN COMPLEMENTARIO, PACIENTE PRIORIZADO y PARTICULAR.

## Reglas de negocio
- **Color por estancia**: Amarillo (#F2FF82) de 6 a 8 días de estancia, naranja (#FFB982) de 9 a 14 días y rojo (#FF8F82) de 15 días o más.
- **Color por pendiente**: Azul claro (#ADD8E6) para solicitud de cama pendiente, verde (#90EE90) para solicitud de gestión clínica pendiente y lila (#C8A2C8) para dieta pendiente.
- **Prioridad de colores**: Se aplica el primer criterio que se cumpla en este orden: estancia de 6 a 8, de 9 a 14, de 15 o más, cama, gestión clínica y dieta; estancias menores de 6 días sin pendientes quedan sin color.
- **Gestión clínica pendiente**: PENDIENTES_GESTION vale «PENDIENTE SOLICITUD GESTION CLINICA» cuando el paciente tiene OID_GESTION; si no, queda vacío.

## Observaciones
- **Nombre de página**: La página se llama LISTADO en Power BI; la documentación original la llama «NAOS -LISTADO».
- **Color oculta pendientes**: Por la prioridad del color, un paciente con 6 o más días de estancia no muestra si además tiene cama, gestión clínica o dieta pendiente.
- **Clasificación sin documentar**: El modelo no tiene una columna CLASIFICACION: el gráfico «CLASIFICACIÓN» usa PACIENTES[TIPO_PACIENTE], que vale MEDICINA PREPAGADA, PLAN COMPLEMENTARIO, PÓLIZA o PACIENTE PRIORIZADO.
- **Columnas de la tabla**: Según el PBIR, la tabla de detalle muestra PACIENTE, EDAD, DOCUMENTO, INGRESO, SERVICIO, CAMA, EPS, FAMILIAR VOCERO, TELEFONO FAMILIAR VOCERO, TIPO PACIENTE, SOLICITUD CAMA, PENDIENTES GESTION CLINICA y DIETAS (columnas de PACIENTES).

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
- **2026-11-03 · v3**: Columnas de la tabla y campo del gráfico por clasificación tomados del PBIR; el modelo no tiene PACIENTES[CLASIFICACION]. Autor: agente dic-pendientes.
- **2026-11-03 · v4**: Resultados de la consulta naos-01 contra el modelo publicado (2026-11-03) Autor: agente dic-pendientes.
