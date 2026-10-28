---
tablero: ASIGNACION DE CITAS
pagina: GENERAL
nombre_funcional: Seguimiento de solicitudes de citas de especialistas, asignaciones y agenda
bloque: General
tablas: [EN_ESPERA, CITAS_ASIGNADAS, AGENDA_ESPECIALISTAS, ASEGURADORA, ASESORES, ESPECIALIDADES, PACIENTES, PACIENTES CITA ASIGNADA, Calendario]
actualizado: 2026-10-20
version: 1
---

# GENERAL

## Propósito
Monitorea las solicitudes de citas con especialistas que entran al sistema: cuántas siguen en espera, cuántas se asignaron, cuántos días tarda la asignación y cómo se reparte el trabajo entre especialidades, aseguradoras y asesores del área de citas. También muestra la agenda disponible de los especialistas. Las demás páginas están ocultas en la barra de páginas y se abren con los botones de INICIO, salvo DISPONIBILIDAD X ESPECIALIDAD y DETALLE CITAS ASIGNADAS DÍA, que no tienen botón. Todas las tablas son importadas (se actualizan con el refresco del modelo) y el análisis es por año, mes y día.

## Fuentes de datos
- **EN_ESPERA**: Solicitudes de cita por especialidad (lista de espera de Dinámica, CMNCITESP) unidas a los preagendamientos de la planilla de usuarios (estado 0 y con teléfono). Una fila por solicitud, registradas desde 2024-04-01 hasta hoy; modo import.
- **CITAS_ASIGNADAS**: Citas médicas asignadas en Dinámica (CMNCITMED) con fecha de asignación desde 2024-04-01 hasta hoy, una fila por cita, sin los pacientes excluidos; modo import.
- **AGENDA_ESPECIALISTAS**: Agenda de cada especialista por bloque y día (minutos abiertos, citas asignadas y cupos restantes), desde 2024-04-01 hasta 60 días después de hoy, solo para una lista fija de unos 100 códigos de médico; modo import.
- **ASEGURADORA**: Contratos de aseguradoras (DIM_ASEGURADORA) con su tercero y dos agrupaciones homologadas; modo import.
- **ASESORES**: Usuarios de Dinámica con rol CITAS; modo import.
- **ESPECIALIDADES**: Catálogo de especialidades de Dinámica (genespeci); modo import.
- **PACIENTES**: Dimensión de pacientes (dim_pacientes); aporta el correo electrónico; modo import.
- **PACIENTES CITA ASIGNADA**: Solicitudes en espera con la primera cita posterior del mismo paciente y especialidad, si existe; modo import.
- **Calendario**: Tabla calculada CALENDAR("2024-04-01", TODAY()+30) con la columna DIA_SEMANA (1.LUNES a 7.DOMINGO).

## Definiciones
- **Solicitud en espera**: Pedido de cita con un especialista registrado en la lista de espera. Su fecha (EN_ESPERA[FECHA] y FECHA_HORA) es CCEFECREG, la fecha de registro del estado actual de la solicitud; en las que siguen en espera coincide con el registro de la solicitud.
- **Estado de la solicitud**: EN_ESPERA[CCEESTADO]: 0 en espera, 1 asignada, 2 eliminada. Columna EN_ESPERA[ESTADO_CITA] con esos textos.
- **Estado de la cita asignada**: CITAS_ASIGNADAS[CCMESTADO]: 0 registrada (pendiente de atención), 1 anulada o cancelada, 2 confirmada (asistida), 3 inasistida.
- **Cita asignada (conteo)**: CITAS_ASIGNADAS[Asignada] vale 1 para todo estado distinto de 1 (anulada); incluye registradas, asistidas e inasistidas.
- **Asesor**: Usuario de Dinámica con rol CITAS que gestiona la solicitud o asigna la cita. Columna ASESOR = UPPER(NOMBRE_USUARIO).
- **Tramo horario**: Hora de registro o de asignación redondeada hacia abajo a la media hora (por ejemplo 08:00 AM u 08:30 AM).
- **Días en espera**: EN_ESPERA[DIAS_ESPERA] = DATEDIFF(EN_ESPERA[FECHA],TODAY(),DAY); días desde el registro de la solicitud hasta hoy.
- **Días para asignación**: EN_ESPERA[Tiempo_Asignacion] = DATEDIFF(EN_ESPERA[FECHA_HORA],EN_ESPERA[fecha_asignacion],DAY); días entre el registro de la solicitud y la asignación de la primera cita posterior del mismo paciente y especialidad.
- **No registrado en Dinámica**: Solicitud sin paciente en Dinámica (viene del preagendamiento). EN_ESPERA[Existe] = «NO EXISTE EN DINAMICA» y EN_ESPERA[EN_ESPERA_NO_DINAMICA] = 1 cuando además está en espera.
- **Pendiente sin gestión**: EN_ESPERA[PENDIENTES_CO] vale 1 si la solicitud está en espera y no tiene ninguna gestión con estado distinto de 0.
- **Clasificación de entidad**: EN_ESPERA[MAESTROS]: MAGISTERIO (códigos EPS2803, EPS2885, EPS2886, EPS28A1, EPS2873, EPS2810, EPS280), PARTICULAR (PART6607, PART6656, PART6675, PART6679, PART6690, PART66, PART6608), MEDICINA PREPAGADA (tipo de entidad 4) y OTROS.
- **Aseguradora homologada**: ASEGURADORA[ASEGURADORA_HM] agrupa los contratos de un mismo tercero bajo un nombre corto (NUEVA EPS, SURA, ALLIANZ SEGUROS DE VIDA, COLMEDICA, SALUD TOTAL, SANITAS, COOMEVA EPS, COLSANITAS, ASMET SALUD, entre otros); el resto conserva el nombre del contrato.
- **Medicina prepagada y particulares**: ASEGURADORA[ASEGURADORA_HOMOLOGADA] agrupa en «MEDICINA PREPAGADA Y PARTICULARES» una lista fija de códigos de contrato y todo código que contenga «MP»; el resto toma el nombre del tercero.

## Reglas de negocio
- **Periodo de datos**: Solicitudes y citas desde 2024-04-01 hasta hoy; agenda hasta 60 días adelante; calendario hasta 30 días adelante.
- **Pacientes excluidos**: CITAS_ASIGNADAS y AGENDA_ESPECIALISTAS excluyen una lista fija de 21 identificadores internos de paciente; por confirmar si son pacientes de prueba. EN_ESPERA no aplica esa exclusión.
- **Una fila por solicitud o cita**: Las consultas conservan solo la primera fila de cada solicitud o cita (RN = 1).
- **Filtros de fecha**: Los segmentadores de año, mes y día usan Calendario, que filtra EN_ESPERA por fecha de registro, CITAS_ASIGNADAS por fecha de asignación y AGENDA_ESPECIALISTAS por fecha de agenda.
- **Segmentador de aseguradora**: En la mayoría de páginas el filtro «ASEGURADORA» usa EN_ESPERA[NOM_TERCERO], el tercero del contrato actual del paciente.

## Observaciones
- **Etiquetas de estados cruzadas**: El estado 3 se rotula «CITAS INASISTIDAS» en INICIO pero «CANCELADAS» o «CITAS CANCELADAS» en ASIGNADAS X ASESOR y COMPARATIVO ASIGNADAS; el estado 1 se rotula «CITAS CANCELADAS» en INICIO y «ANULADAS» en esas páginas.
- **Documentación frente al modelo**: La documentación llama columnas calculadas a %INASISTENCIA y %PENDIENTE (en el modelo son medidas) y medida a PENDIENTES (en el modelo es columna calculada). Prevalece el modelo.
- **Páginas sin documentación del propietario**: DISPONIBILIDAD X ESPECIALIDAD y DETALLE CITAS ASIGNADAS DÍA existen en el PBIP pero no en la documentación; se documentaron solo con el PBIP.
- **Fecha de las solicitudes asignadas**: Para solicitudes ya asignadas, EN_ESPERA[FECHA] sería la fecha del cambio a asignada y no la de creación de la solicitud, lo que afecta los días para asignación. Por confirmar.
- **Asignación tomada de la cita posterior**: La fecha de asignación de una solicitud es la de una cita registrada (estado 0) posterior del mismo paciente y especialidad; si hay varias, la consulta no fija cuál toma.
- **Tabla MEDIDAS vacía**: Existe una tabla MEDIDAS sin medidas; las dos medidas del modelo están en CITAS_ASIGNADAS.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
