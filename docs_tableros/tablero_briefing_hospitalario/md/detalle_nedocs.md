---
tablero: BRIEFING HOSPITALARIO
pagina: DETALLE NEDOCS
nombre_funcional: Nivel de sobreocupación de urgencias con la escala NEDOCS
bloque: Día
tablas: [NEDOCS]
actualizado: 2026-10-20
version: 1
---

# DETALLE NEDOCS

## Propósito
Muestra el valor actual del NEDOCS, su clasificación, las siete variables que lo componen y la fórmula con los valores reales reemplazados. Sirve para detectar temprano la congestión del servicio de urgencias. Se llega desde el botón DETALLE NEDOCS de la tarjeta NEDOCS en INICIO.

## Fuentes de datos
- **NEDOCS**: Tabla GH_NEDOCS de PLANILLAUSUARIO con las variables A1, A2, B1, B2, C, D y E del momento.

## Indicadores
- **NEDOCS**: Puntaje de sobreocupación de urgencias. Medida TotalN = -20 + 85.8 * (SUM(A1) / SUM(A2)) + 600 * (SUM(B1) / SUM(B2)) + 5.64 * SUM(C) + 0.93 * SUM(D) + 13.4 * SUM(E).
- **A1 pacientes en urgencias**: Pacientes ocupando cama de urgencias. SUM(NEDOCS[A1]).
- **A2 camas de urgencias**: Camas en el servicio de urgencias. SUM(NEDOCS[A2]).
- **B1 pacientes esperando cama**: Pacientes de urgencias esperando cama de hospitalización. SUM(NEDOCS[B1]).
- **B2 camas hospitalarias**: Total de camas hospitalarias. SUM(NEDOCS[B2]).
- **C espera de consulta**: Tiempo de espera para consulta del último paciente triagizado. SUM(NEDOCS[C]); unidad por confirmar.
- **D espera de cama**: Tiempo de espera para asignación de cama del último paciente triagizado. SUM(NEDOCS[D]); unidad por confirmar.
- **E pacientes intubados**: Pacientes intubados en urgencias. SUM(NEDOCS[E]).

## Visuales
- **Tarjeta NEDOCS**: Valor de TotalN con la clasificación (columna etiqueta) como título.
- **Leyenda de rangos**: Recuadro con NORMAL 0-60, OCUPADO 61-100, SOBREOCUPADO 101-140, SEVERAMENTE SOBREOCUPADO 141-180 y CRITICAMENTE SOBREOCUPADO >180, cada uno con su color.
- **Tarjetas de variables**: Siete tarjetas, una por variable, con los títulos del PBIP (por ejemplo PACIENTES OCUPANDO CAMA DE URGENCIAS).
- **Fórmula con valores**: Visual HTML con la medida TextoConResultadoHTML, que muestra la fórmula con los valores reales en rojo y el resultado en negrita.

## Reglas de negocio
- **Clasificación NEDOCS**: Normal de 0 a 60,99; Ocupado de 61 a 100,99; Sobreocupado de 101 a 140,99; Severamente sobreocupado de 141 a 180,99; Críticamente sobreocupado de 181 en adelante (columna etiqueta).
- **División por cero**: TextoConResultadoHTML reemplaza por 0 los términos A1/A2 y B1/B2 cuando A2 o B2 valen 0; TotalN no lo hace.

## Observaciones
- **Valores entre rangos**: La columna etiqueta deja sin clasificación los valores negativos y los que caen entre 180,99 y 181.
- **Descripción de A2**: La documentación describe A2 como «camas disponibles en el servicio», pero la tarjeta dice CAMAS EN EL SERVICIO DE URGENCIAS. Por confirmar si son camas totales o disponibles.
- **Unidades de C y D**: En la escala NEDOCS estándar los tiempos van en horas; la documentación no lo indica. Por confirmar.
- **Medida repetida**: La documentación original repite dos veces TotalN y TextoConResultadoHTML.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial a partir de la documentación del propietario y del PBIP.
