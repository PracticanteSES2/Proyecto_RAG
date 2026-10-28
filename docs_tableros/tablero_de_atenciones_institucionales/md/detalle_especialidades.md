---
tablero: TABLERO DE ATENCIONES INSTITUCIONALES
pagina: DETALLE ESPECIALIDADES
nombre_funcional: Consultas ambulatorias y oportunidad por especialidad
bloque: Histórico
tablas: [CONSULTAS_AMBULATORIAS, Calendario]
actualizado: 2026-10-28
version: 2
---

# DETALLE ESPECIALIDADES

## Propósito
Muestra cómo se reparten las consultas ambulatorias entre las especialidades y la oportunidad en días de la consulta general, de control y de primera vez. Se llega desde el botón DETALLE ESPECIALIDADES de CONSULTAS AMBULATORIAS; es una página oculta de navegación.

## Fuentes de datos
- **CONSULTAS_AMBULATORIAS**: Citas de consulta externa con folio, especialidad agrupada, asegurador, fechas de asignación y de cita, primera vez o control y estado de la cita; es la misma tabla de CONSULTAS AMBULATORIAS.

## Indicadores
- **Total consultas año anterior**: Consultas del año anterior. Medida por confirmar.
- **Promedio mensual año anterior**: Consultas del año anterior divididas por sus meses. Medida por confirmar.
- **Oportunidad de la consulta**: Promedio de días entre la asignación de la cita y la cita. Medida Promedio_Dinamico: con filtro de fecha usa promedio_asignacion = AVERAGE(CONSULTAS_AMBULATORIAS[DIAS_REAL]); sin filtro muestra el último mes cerrado. Unidad: días.

## Visuales
- **Segmentadores**: ASEGURADOR (lista desplegable de selección múltiple), Año (sobre Calendario[Date], sin 2023 ni vacíos), Mes, ESTADO y ESPECIALIDAD.
- **Tarjetas de consultas**: «TOTAL CONSULTAS AÑO ANTERIOR» y «PROMEDIO MENSUAL AÑO ANTERIOR».
- **Mapa de árbol por especialidad**: Treemap «CONSULTAS AMBULATORIAS POR ESPECIALIDAD» con el número de consultas de cada especialidad.
- **Medidor consulta general**: «OPORTUNIDAD CONSULTA GENERAL» con máximo de 20 días.
- **Medidor consulta de control**: «OPORTUNIDAD CONSULTA CONTROL» con Promedio_Dinamico, filtros ESTADO_CITA = CUMPLIDA y PV_CONTROL = Control; máximo del eje = promedio de la columna CONTROL (20 días).
- **Medidor consulta primera vez**: «OPORTUNIDAD CONSULTA PRIMERA VEZ» con Promedio_Dinamico, filtros ESTADO_CITA = CUMPLIDA y PV_CONTROL = Primera Vez; máximo del eje = promedio de la columna CONSULTA_PRA (15 días).
- **Botón de regreso**: Botón con icono de inicio que navega a otra página del informe.

## Reglas de negocio
- **Exclusión de gastroenterología sin consulta**: Filtro de página ESPECIALIDAD distinta de GASTROENTEROLOGIA_QUITAR.
- **Solo citas cumplidas**: Los medidores de control y primera vez solo promedian citas en estado CUMPLIDA.
- **Metas de oportunidad**: 20 días para consulta general y de control, 15 días para primera vez (columnas GENERAL, CONTROL y CONSULTA_PRA).

## Observaciones
- **PBIP parcial**: El PBIP de esta página solo trae los segmentadores ASEGURADOR y Año, los medidores de control y primera vez y el botón; las tarjetas, el treemap, el medidor general y los segmentadores Mes, ESTADO y ESPECIALIDAD salen de la documentación.
- **Filtros de página sin valor**: La página tiene filtros sobre ESTADO_CITA y TIPO_ATENCION sin valores elegidos y uno oculto sobre CONSULTA_URGENCIAS[FECHA_FOLIO] sin valores; hoy no filtran nada.
- **Destino del botón**: El botón con icono de inicio no apunta a la página que parece ser INDICADORES en el PBIP. Destino por confirmar.
- **Nombre compartido**: El botón que lleva a ESPECIALIDADES CIRUGIA también dice «DETALLE ESPECIALIDADES»; son páginas distintas.
- **Medidor general**: La documentación no indica la medida ni los filtros del medidor de consulta general. Por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
