---
tablero: TABLERO LAVANDERIA
pagina: DICCIONARIO
nombre_funcional: Diccionario de variables del tablero
bloque: Diccionario
tablas: [LAVANDERIA]
actualizado: 2026-10-28
version: 2
---

# DICCIONARIO

## Propósito
Diccionario de variables del tablero TABLERO LAVANDERIA: qué es la tabla LAVANDERIA, sus columnas calculadas y las columnas clave del modelo «TABLERO LAVANDERIA». El modelo tiene una sola tabla de hechos y no tiene medidas DAX; los totales se obtienen sumando LAVANDERIA[Peso].

## Tablas
- **LAVANDERIA**: Cada fila es un pesaje de ropa hospitalaria que ingresa a lavandería, con su peso, el servicio de origen, el turno y el colaborador que lo registra. Origen: consulta SQL sobre PLANILLAUSUARIO.DBO.Cp_PesajeLavanderia, PLANILLAUSUARIO.DBO.Cp_EncabezadoLavanderia, PLANILLAUSUARIO.DBO.Cp_Medicion, PLANILLAUSUARIO.DBO.USUARIO en la base DWSES (Import). Granularidad: una fila por pesaje (Cp_PesajeLavanderia), con los datos de su encabezado (fecha y turno), su servicio y su usuario. Columnas principales: Fecha, FechaRegistro, NOMBRE_COMPLETO, OID, OidUsuario, Peso, SERVICIO, Turno y 3 más.

## Columnas calculadas
- **LAVANDERIA[NOMBRE_COMPLETO]**: Nombre completo del colaborador que registró el pesaje (nombres y apellidos unidos con un espacio). Es la fila de la matriz USUARIO QUE REGISTRA. Tipo: texto. Cálculo: `CONCATENATE(LAVANDERIA[usu_nombres],CONCATENATE(" ",LAVANDERIA[usu_apellidos]))`. Se usa en: la documentación del propietario lo usa en la matriz USUARIO QUE REGISTRA y en el gráfico PESO por TURNO; el PBIP local no trae visuales.
- **LAVANDERIA[TURNO_OK]**: Turno laboral en texto: 1 es MAÑANA, 2 es TARDE y 3 es NOCHE. Cualquier otro valor o turno vacío queda en blanco y se ve como (En blanco) en el gráfico de turnos. Tipo: texto. Cálculo: `IF(LAVANDERIA[Turno]=1, "MAÑANA", IF(LAVANDERIA[Turno]=2,"TARDE", IF(LAVANDERIA[Turno]=3,"NOCHE")))`. Se usa en: la documentación del propietario lo usa en el gráfico PESO por TURNO; el PBIP local no trae visuales.

## Columnas clave
- **LAVANDERIA[Peso]**: Peso de ropa registrado en cada pesaje. Tipo: decimal. Valores: número positivo por pesaje; la unidad (kilogramos o libras) no está documentada. Se usa en: Página 1 según la documentación del propietario (el PBIP local no trae visuales): la matriz de participación por servicio, la matriz USUARIO QUE REGISTRA y los gráficos PESO por TURNO y PESO TOTAL por Mes (suma de la columna)
- **LAVANDERIA[SERVICIO]**: Servicio u origen de la ropa pesada (nombre en Cp_Medicion). Tipo: texto. Valores: nombres de servicios del hospital; no se enumeran en la documentación. Se usa en: Página 1 según la documentación del propietario (el PBIP local no trae visuales): filas de la matriz de participación por servicio.
- **LAVANDERIA[Turno]**: Código del turno laboral del encabezado del pesaje. Tipo: entero. Valores: 1 mañana, 2 tarde y 3 noche (los traduce TURNO_OK). Se usa en: Página 1 según la documentación del propietario (el PBIP local no trae visuales): base de TURNO_OK.
- **LAVANDERIA[Fecha]**: Fecha del encabezado del pesaje (Cp_EncabezadoLavanderia). Tipo: fecha. Es una de las dos fechas con tabla de fechas automática; cuál alimenta los segmentadores de Año y Mes está por confirmar. Se usa en: Página 1 según la documentación del propietario (el PBIP local no trae visuales): posible origen de los segmentadores de Año y Mes y de las columnas por mes.
- **LAVANDERIA[FechaRegistro]**: Fecha y hora en que el colaborador registró el pesaje en el sistema. Tipo: fecha. Es la otra fecha con tabla de fechas automática; puede diferir de Fecha. Se usa en: Página 1 según la documentación del propietario (el PBIP local no trae visuales): posible origen de los segmentadores de Año y Mes.
- **LAVANDERIA[OidUsuario]**: Identificador del usuario que registró el pesaje; enlaza con USUARIO (usu_oid) para obtener nombres y apellidos. Tipo: entero. Se usa en: solo para traer el nombre del colaborador (NOMBRE_COMPLETO)

## Observaciones
- **Unidad del peso**: La documentación no indica si el peso está en kilogramos o libras. Por confirmar con el dueño del tablero.
- **Fecha de los filtros**: No se sabe si los segmentadores de Año y Mes usan Fecha (encabezado) o FechaRegistro (pesaje). Por confirmar.
- **PBIP sin visuales**: El PBIP local solo trae la página «Página 1» sin visuales; la descripción de visuales proviene de la documentación del propietario.
- **Pendientes para el dueño**: Confirmar unidad del peso, fecha que usan los filtros y significado de los pesajes sin turno, sin servicio o sin usuario (aparecen como (En blanco))
- **Sin medidas DAX**: El modelo no tiene medidas; los totales salen de sumar LAVANDERIA[Peso] en cada visual y el cálculo del porcentaje de participación no está en el modelo (se define en el visual). Por confirmar.

## Historial de cambios
- **2026-10-28 · v1**: Esqueleto generado desde data/model_metadata/tablero_lavanderia y hechos del PBIP.
- **2026-10-28 · v2**: Diccionario y revisión contra el modelo y el informe.
