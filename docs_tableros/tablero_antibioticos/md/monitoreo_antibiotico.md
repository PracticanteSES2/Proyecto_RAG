---
tablero: TABLERO ANTIBIOTICOS
pagina: MONITOREO_ANTIBIOTICO
nombre_funcional: Pacientes con antibiótico activo por tipo de antibiótico y por servicio
bloque: Día
tablas: [ANTIBIOTICOS]
actualizado: 2026-10-28
version: 2
---

# MONITOREO_ANTIBIOTICO

## Propósito
Muestra cuántos pacientes hospitalizados tienen tratamiento antibiótico activo, distribuidos por antibiótico y por servicio, junto con el total de dosis suministradas. Sirve para identificar los antibióticos más usados y los servicios con más tratamientos. Se llega desde el botón MONITOREO ANTIBIOTICO de la página ANTIBIOTICOS; la flecha superior regresa. La página está oculta en modo vista.

## Fuentes de datos
- **ANTIBIOTICOS**: Aplicaciones de antibióticos de los pacientes que ocupan cama, con su estado de tratamiento.

## Indicadores
- **Pacientes activos**: Pacientes distintos (por documento) con algún antibiótico en estado ACTIVO. Medida PAC_ACT.
- **Total dosis suministradas**: Suma de la cantidad aplicada (HCCANTIDAD) de las aplicaciones del contexto. Medida TOTAL DOSIS SUMINISTRADAS = SUM(ANTIBIOTICOS[HCCANTIDAD]).

## Visuales
- **Segmentadores**: ANTIBIOTICO, Date Año y Date Mes1 (año y mes de Calendario[Date], la fecha de aplicación) y SERVICIO.
- **PACIENTES ACTIVOS POR TIPO DE ANTIBIÓTICO**: Barras horizontales con PAC_ACT por ANTIBIOTICO, de mayor a menor.
- **PACIENTES ACTIVOS POR SERVICIO**: Anillo con PAC_ACT por SERVICIO (número y porcentaje), de mayor a menor.
- **Tarjetas**: PACIENTES ACTIVOS (PAC_ACT) y TOTAL DOSIS SUMINISTRADAS (suma de HCCANTIDAD).
- **Botón de regreso**: Flecha que vuelve a la página ANTIBIOTICOS.

## Reglas de negocio
- **Conteo por antibiótico**: Un paciente con dos antibióticos activos cuenta en la barra de cada uno, por eso la suma de las barras puede superar el total de pacientes activos.

## Observaciones
- **Nombre de página**: La página se llama MONITOREO_ANTIBIOTICO en Power BI (con guion bajo); el botón de ANTIBIOTICOS se rotula MONITOREO ANTIBIOTICO y la página está oculta en modo vista.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
