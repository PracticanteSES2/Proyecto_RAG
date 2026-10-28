---
tablero: TABLERO ANTIBIOTICOS
pagina: GENERAL
nombre_funcional: Uso de antibióticos en pacientes hospitalizados
bloque: General
tablas: [ANTIBIOTICOS]
actualizado: 2026-10-28
version: 2
---

# GENERAL

## Propósito
Tablero de dos páginas para monitorear el uso de antibióticos en los pacientes que ocupan cama: aplicaciones registradas, pacientes con tratamiento activo, detalle por paciente y distribución por antibiótico y servicio. Apoya decisiones clínicas, farmacéuticas y administrativas. La página ANTIBIOTICOS tiene un botón MONITOREO ANTIBIOTICO que abre la segunda página, y esta tiene una flecha para volver.

## Fuentes de datos
- **ANTIBIOTICOS**: Aplicaciones de medicamentos del grupo de inventario 36 (antibióticos) registradas en la hoja de enfermería (HCNCONMED) para pacientes que hoy ocupan una cama, con paciente, documento, cama, servicio, asegurador, ingreso, médico, antibiótico, fecha de aplicación, cantidades y estado del tratamiento. Sin filtro de fechas: trae toda la estancia del paciente.

## Definiciones
- **Antibiótico**: Producto del grupo de inventario con IGRCODIGO = 36; se muestra su descripción corta (IPRDESCOR).
- **Aplicación**: Registro de administración del antibiótico en la hoja de enfermería con HCRESPUES = 0.
- **Fecha de aplicación**: Columna HORA_APLICACION; pese al nombre, guarda solo la fecha (sin hora).
- **Estado del tratamiento (Suspension)**: SUSPENDIDO si la orden tiene marca de suspensión; ACTIVO si la cantidad despachada supera la cantidad aplicada; en otro caso FINALIZADO.
- **Paciente activo**: Paciente con al menos un antibiótico en estado ACTIVO.

## Reglas de negocio
- **Pacientes en cama**: Solo pacientes asignados a una cama con estado distinto de 6 (HCAESTADO <> 6).
- **Aplicaciones válidas**: Solo registros con HCRESPUES = 0.

## Observaciones
- **Significado de códigos**: Qué representan HCAESTADO = 6 y HCRESPUES = 0 no está documentado. Por confirmar.
- **Estado ACTIVO por despacho**: El estado ACTIVO se infiere de la diferencia entre unidades despachadas (HCSCANDESP) y aplicadas, no de una orden médica vigente. Por confirmar con farmacia.
- **Medida distinta de la documentación**: La documentación describe TOTAL ATB (conteo de paciente, antibiótico y día); las tarjetas usan TOTAL DOSIS SUMINISTRADAS = SUM(HCCANTIDAD), que suma cantidades.
- **Calendario**: La tabla Calendario (de 2023-01-01 a hoy) se relaciona con la fecha de aplicación y alimenta los segmentadores de año y mes.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
