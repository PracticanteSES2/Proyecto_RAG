---
tablero: BRIEFING HOSPITALARIO
pagina: SOLICITUD CAMAS
nombre_funcional: Solicitudes de cama pendientes por servicio, sexo y aseguradora
bloque: Día
tablas: [SOLICITUD CAMAS, SERVICIO SOLICITUD]
actualizado: 2026-10-20
version: 1
---

# SOLICITUD CAMAS

## Propósito
Lista las solicitudes de cama hospitalaria que aún no tienen cama asignada, con el total, la división por sexo y el detalle por paciente, servicio y EPS. Sirve para priorizar la asignación según antigüedad, servicio y aseguradora. Se llega desde el botón DETALLE SOLICITUD CAMAS del visual CAMAS SOLICITADAS POR SERVICIO en INICIO.

## Fuentes de datos
- **SOLICITUD CAMAS**: Solicitudes de cama (fact_solicitud_cama) unidas con ingreso, paciente, unidad, aseguradora, dependencia y tercero. Trae sexo, nombre y documento del paciente, servicio (HSUNOMBRE y GDPNOMBRE), plan (GDENOMBRE) y aseguradora (TERNOMCOM).

## Indicadores
- **Solicitudes**: Número de solicitudes de cama pendientes. DISTINCTCOUNT(SOLICITUD CAMAS[oid]).
- **Hombres**: Solicitudes de pacientes con sexo HOMBRE (GPASEXPAC = 1).
- **Mujeres**: Solicitudes de pacientes con sexo MUJER (GPASEXPAC = 2).

## Visuales
- **Tarjetas**: SOLICITUDES, HOMBRES y MUJERES.
- **Segmentadores**: TIPO (condición especial de la cama), SERVICIO SOLICITADO, sexo (casillas HOMBRE y MUJER) y ASEGURADORA.
- **Botones por área**: GENERAL, HOSPITALIZACIÓN, URGENCIAS, GINECOBSTETRICIA, SEXTO PISO, CUIDADO CRÍTICO, QUIROFANO, HOSPITALIZACIÓN PARCIAL y UNIDAD NEUROCARDIOVASCULAR; cada uno aplica un marcador con los servicios del área.
- **Botón GESTIÓN DE CAMAS**: Navega a una página de gestión de camas; por confirmar si es GESTIÓN DE CAMAS o DETALLE GESTIÓN CAMAS.
- **Tabla de solicitudes**: ID SOLICITUD, PACIENTE, SERVICIO, EPS y FECHA DE CREACIÓN de cada solicitud.

## Reglas de negocio
- **Solicitud pendiente**: Se muestran solicitudes con estadooid 2 o 3 (filtro aplicado en los marcadores y en INICIO) y, en INICIO, sin cama asignada (camaoid vacío).
- **Columna RESPUESTA**: ASIGNADA si estadooid es 4, 5 u 8; en otro caso NO ASIGNADA.
- **Columna TIPO**: AISLAMIENTO, REJAS, SUCCIÓN o UNIPERSONAL según la marca de la solicitud, en ese orden de prioridad.
- **Columna SERVICIO_SOLICITADO**: ServicioCama 1 es HOSPITALIZACIÓN GENERAL, 2 HOSPITALIZACIÓN INTERMEDIOS y 3 UNIDADES DE CUIDADOS INTENSIVOS.
- **Columna SERVICIO SOLICITUD**: Homologa serviciooid a un código interno de servicio (por ejemplo 1→16, 18→14, 38→1); valores no listados quedan en 0.

## Observaciones
- **Propósito copiado**: El texto de propósito de la documentación original es el mismo de GESTIÓN CAMAS (habla de camas ocupadas y disponibles); se redactó de nuevo a partir de los visuales.
- **Significado de estados**: El significado de los estados 2, 3, 4, 5 y 8 de la solicitud no está documentado. Por confirmar.
- **Nombre de página**: La página se llama SOLICITUD CAMAS en Power BI; el botón de INICIO dice DETALLE SOLICITUD CAMAS.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
