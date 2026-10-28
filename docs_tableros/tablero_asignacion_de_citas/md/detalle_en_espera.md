---
tablero: ASIGNACION DE CITAS
pagina: DETALLE EN ESPERA
nombre_funcional: Listado de pacientes con solicitud de cita en espera
bloque: Histórico
tablas: [EN_ESPERA, PACIENTES CITA ASIGNADA, PACIENTES, Calendario]
actualizado: 2026-10-28
version: 2
---

# DETALLE EN ESPERA

## Propósito
Lista, paciente por paciente, las solicitudes de cita con especialista que siguen en espera, con sus días de espera y, si existe, la cita que ya se le asignó después. Sirve como lista de trabajo para contactar pacientes. Se llega desde el botón DETALLE EN ESPERA de INICIO; los datos se filtran por fecha de registro (bloque Histórico).

## Fuentes de datos
- **EN_ESPERA**: Solicitudes en espera (CCEESTADO = 0) con datos de contacto, asesor, especialidad, aseguradora y cita posterior.
- **PACIENTES CITA ASIGNADA**: Indica si el paciente ya tiene una cita posterior en la misma especialidad.
- **PACIENTES**: Aporta el correo electrónico del paciente.

## Indicadores
- **Consultas en espera**: Solicitudes en espera con los filtros aplicados. DISTINCTCOUNT(EN_ESPERA[OID_CITA]).
- **Días en espera**: Días desde el registro de la solicitud hasta hoy. Columna EN_ESPERA[DIAS_ESPERA].

## Visuales
- **Filtros de la página**: Segmentadores de ASESOR (EN_ESPERA[NOMBRE_USUARIO]), ESPECIALIDAD, «Date Año», «Date Mes» y «Date Día» (año, mes y día), ASEGURADORA (EN_ESPERA[NOM_TERCERO]) y buscadores de texto «NOMBRE PACIENTE» (EN_ESPERA[gpanomcom]) y «DOCUMENTO PACIENTE» (EN_ESPERA[pacnumdoc]).
- **Filtros por casillas**: TIENE CITA (TIENE CITA ASIGNADA o NO TIENE CITA ASIGNADA), Existe (EXISTE EN DINAMICA o NO EXISTE EN DINAMICA) y clasificación MAESTROS.
- **Tarjeta consultas en espera**: Total de solicitudes en espera.
- **Tabla de pacientes en espera**: Fecha de solicitud, documento, nombre, teléfono, asesor, especialidad, DIAS EN ESPERA, FECHA DE CITA ASIGNADA, MEDICO SOLICITADO, ASESOR CITA ASIGNADA, ASEGURADORA y CORREO ELECTRONICO.
- **Botón inicio**: Regresa a INICIO.

## Reglas de negocio
- **Solo solicitudes en espera**: Filtros de página CCEESTADO = 0 y OID_CITA no vacío.
- **Cita posterior**: FECHA DE CITA ASIGNADA y ASESOR CITA ASIGNADA vienen de la primera cita registrada (estado 0) del mismo paciente y especialidad con fecha posterior al registro de la solicitud.
- **Tiene cita asignada**: PACIENTES CITA ASIGNADA[TIENE CITA] es «TIENE CITA ASIGNADA» cuando existe esa cita posterior.

## Observaciones
- **Médico solicitado**: EN_ESPERA[MEDICO] solo tiene valor en solicitudes del preagendamiento; en las de Dinámica la consulta lo deja vacío.
- **Datos personales**: La tabla muestra nombre, documento, teléfono y correo del paciente; el RAG no debe transcribirlos.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
