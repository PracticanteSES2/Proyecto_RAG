---
tablero: ASIGNACION DE CITAS
pagina: COMPARATIVO ASIGNADAS
nombre_funcional: Comparativo porcentual de estados de la gestión de citas por especialidad
bloque: Histórico
tablas: [EN_ESPERA, CITAS_ASIGNADAS, ESPECIALIDADES, ASEGURADORA, Calendario]
actualizado: 2026-10-28
version: 2
---

# COMPARATIVO ASIGNADAS

## Propósito
Compara en porcentaje, para cada especialidad, cómo se reparten las solicitudes y citas entre en espera, no registradas en Dinámica, asignadas en espera, anuladas, canceladas, con asistencia y asignadas. Sirve para seguir el resultado de la gestión de citas por área. La documentación la llama «Comparativo consultas asignadas»; se llega desde el botón COMPARATIVO CONSULTAS ASIGNADAS de INICIO (bloque Histórico).

## Fuentes de datos
- **EN_ESPERA**: Solicitudes en espera, no registradas en Dinámica y asignadas.
- **CITAS_ASIGNADAS**: Citas asignadas con su estado.
- **ESPECIALIDADES**: Eje de especialidades del gráfico.
- **ASEGURADORA**: Filtros de aseguradora homologada.

## Indicadores
- **Consultas en espera**: Solicitudes en espera. SUM(EN_ESPERA[PENDIENTES]).
- **No registrados en Dinámica**: Solicitudes en espera sin paciente en Dinámica. SUM(EN_ESPERA[EN_ESPERA_NO_DINAMICA]).
- **Asignadas en espera**: Solicitudes de la lista de espera ya asignadas. SUM(EN_ESPERA[ASIGNADAS]).
- **Asignadas**: Citas asignadas en el periodo. DISTINCTCOUNT(CITAS_ASIGNADAS[OID_CITA]).

## Visuales
- **Filtros de la página**: Segmentadores «Date Año», «Date Mes» y «Date Día» (año, mes y día), ESPECIALIDAD (ESPECIALIDADES[GEEDESCRI]), ASEGURADORA (ASEGURADORA[ASEGURADORA_HM]) y «TOP 5 ASEGURADORAS».
- **Tarjetas de indicadores**: CONSULTAS EN ESPERA, NO REGISTRADOS EN DINÁMICA, ASIGNADAS EN ESPERA y ASIGNADAS.
- **Barras 100 % por especialidad**: Barras apiladas al 100 % por especialidad con EN ESPERA, PACIENTES NO REGISTRADOS EN DINAMICA, ASIGNADAS EN ESPERA, CITAS ANULADAS (estado 1), CITAS CANCELADAS (estado 3), CITAS CON ASISTENCIA (estado 2) y CITAS ASIGNADAS (estado 0); ordenadas por EN ESPERA de mayor a menor.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Top 5 aseguradoras**: El segmentador «TOP 5 ASEGURADORAS» solo ofrece las 5 aseguradoras homologadas con más solicitudes (DISTINCTCOUNT de EN_ESPERA[OID_CITA]).
- **Especialidades del gráfico**: El gráfico solo muestra especialidades con asignadas en espera y con citas anuladas; considera citas en estados 0, 1, 2 y 3.

## Observaciones
- **Series que se solapan**: PACIENTES NO REGISTRADOS EN DINAMICA es un subconjunto de EN ESPERA, así que esas solicitudes cuentan dos veces en la barra al 100 %.
- **Nombres de estados**: CITAS CANCELADAS es el estado 3 (inasistida en INICIO) y CITAS ASIGNADAS es solo el estado 0 (registrada).

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
