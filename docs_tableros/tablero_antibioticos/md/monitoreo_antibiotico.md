---
tablero: TABLERO ANTIBIOTICOS
pagina: MONITOREO ANTIBIOTICO
nombre_funcional: Pacientes con antibiótico activo por tipo de antibiótico y por servicio
bloque: Día
tablas: [ANTIBIOTICOS]
actualizado: 2026-10-20
version: 1
---

# MONITOREO ANTIBIOTICO

## Propósito
Muestra cuántos pacientes hospitalizados tienen tratamiento antibiótico activo, distribuidos por antibiótico y por servicio, junto con el total de dosis suministradas. Sirve para identificar los antibióticos más usados y los servicios con más tratamientos. Se llega desde el botón MONITOREO ANTIBIOTICO de la página ANTIBIOTICOS; la flecha superior regresa.

## Fuentes de datos
- **ANTIBIOTICOS**: Aplicaciones de antibióticos de los pacientes que ocupan cama, con su estado de tratamiento.

## Indicadores
- **Pacientes activos**: Pacientes distintos con algún antibiótico en estado ACTIVO. Medida PAC_ACT.
- **Total dosis suministradas**: Combinaciones distintas de paciente, antibiótico y fecha de aplicación. Medida TOTAL ATB.

## Visuales
- **Segmentadores**: ANTIBIOTICO, Año, Mes y SERVICIO.
- **PACIENTES ACTIVOS POR TIPO DE ANTIBIÓTICO**: Barras horizontales con PAC_ACT por antibiótico, de mayor a menor.
- **PACIENTES ACTIVOS POR SERVICIO**: Anillo con número y porcentaje de pacientes activos por servicio.
- **Tarjetas**: PACIENTES ACTIVOS y TOTAL DOSIS SUMINISTRADAS.
- **Botón de regreso**: Flecha que vuelve a la página ANTIBIOTICOS.

## Reglas de negocio
- **Conteo por antibiótico**: Un paciente con dos antibióticos activos cuenta en la barra de cada uno, por eso la suma de las barras puede superar el total de pacientes activos.

## Observaciones
- **Nombre de página**: El nombre se toma del botón y del título de la documentación (TABLERO MONITOREO ANTIBIOTICO). Nombre de página en Power BI por confirmar.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
