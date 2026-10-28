---
tablero: TABLERO LAVANDERIA
pagina: GENERAL
nombre_funcional: Peso de ropa hospitalaria recibida en lavandería por servicio, turno y colaborador
bloque: General
tablas: [LAVANDERIA]
actualizado: 2026-10-28
version: 2
---

# GENERAL

## Propósito
Tablero de una página para el área de lavandería. Mide el peso de ropa hospitalaria que entra a lavandería por servicio de origen, por turno y por colaborador que registra, mes a mes. Sirve para conocer la carga de lavandería y la participación de cada servicio.

## Fuentes de datos
- **LAVANDERIA**: Pesajes de lavandería (Cp_PesajeLavanderia de PLANILLAUSUARIO) con peso, fecha de registro, usuario que registra, encabezado del pesaje (fecha y turno) y servicio de origen (Cp_Medicion). Trae todo el histórico, sin filtro de fechas.

## Definiciones
- **Pesaje**: Registro de una cantidad de ropa pesada en lavandería, asociado a un servicio, un turno y un usuario.
- **Peso**: Cantidad pesada en cada registro (columna Peso); unidad por confirmar (posiblemente kilogramos).
- **Turno**: Turno laboral del encabezado del pesaje: 1 MAÑANA, 2 TARDE y 3 NOCHE.
- **Servicio**: Área del hospital de donde proviene la ropa (nombre de Cp_Medicion).
- **Usuario que registra**: Colaborador que hizo el pesaje (NOMBRE_COMPLETO).

## Reglas de negocio
- **Columna TURNO_OK**: Traduce Turno 1, 2 y 3 a MAÑANA, TARDE y NOCHE; otros valores quedan en blanco.
- **Columna NOMBRE_COMPLETO**: Une usu_nombres y usu_apellidos del usuario que registra.

## Observaciones
- **Unidad del peso**: La documentación no indica si el peso está en kilogramos o libras. Por confirmar.
- **Medidas que son columnas**: La documentación lista NOMBRE_COMPLETO y TURNO_OK como medidas, pero son columnas calculadas.
- **PBIP sin visuales**: El PBIP local solo trae una página («Página 1») sin visuales; el detalle de visuales sale de la documentación del propietario.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
