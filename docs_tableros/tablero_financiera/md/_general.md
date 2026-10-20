---
tablero: TABLERO FINANCIERA
pagina: GENERAL
nombre_funcional: Facturación, devoluciones, ingresos abiertos, CUPS, costos y rentabilidad
bloque: General
tablas: [FACTURACION, FACTU_AREA, FACTURACION_PENDIENTE, REFACTURACION, FACTURACION_DIARIA, INGRESOS_AB_DIARIO, CONSOLIDADO_INGRESOS_ABIERTOS+, CUPS, COSTOS, ANALISIS_RENTABILIDAD, ACTIVIDADES, TERCEROS, AcreedoresConFactura, AREAS DE SERVICIO, FiltroRefacturacion, CALENDARIO]
actualizado: 2026-10-20
version: 1
---

# GENERAL

## Propósito
Tablero financiero del hospital. Muestra la facturación, las devoluciones (refacturación), los ingresos abiertos (servicios todavía sin facturar), la facturación del mes en curso, la frecuencia y el valor por CUPS, y el costo y la rentabilidad por CUPS. Sirve para seguir el mes anterior, comparar meses y años y ver cuánto aporta cada asegurador (EPS) y cada servicio.

Se entra por INICIO, la única página visible; las otras 17 están ocultas en la barra de páginas y se abren con botones. Seis de ellas no tienen ningún botón que llegue desde INICIO (copias o versiones anteriores).

## Fuentes de datos
- **FACTURACION**: Facturación por orden y área de servicio con el tercero que paga; columnas TOTALAREASERVORDEN (valor facturado), VLRENTIDADORDEN (valor a cargo de la entidad, por confirmar), NOMBRETERCERO y OID_TERCERO. Guarda las medidas NETA, Facturacion_2025_Mensual y Facturacion_2026.
- **FACTU_AREA**: Facturación por área de servicio con CLASIFICACION_SERVICIO y TOTALAREASERVORDEN. Por confirmar en qué se diferencia de FACTURACION.
- **FACTURACION_PENDIENTE**: Ingresos abiertos con valor VLSERVICIO, total TOTAL_ING_ABIERTOS, TERCERO y CLASIFICACION_SERVICIO.
- **REFACTURACION**: Devoluciones de facturas con valor VLRAREASERVICIO, TERCERO, CLASIFICACION_SERVICIO y NUEVOS_INGRESOS.
- **FACTURACION_DIARIA**: Facturación del día a día con TOTALAREASERV, SERVICIO_R, NOMBRETERCERO y las marcas FACTUCOPAGO (factura de copago) y RECAUDADO_FRANQUICIA (recaudado por franquicia).
- **INGRESOS_AB_DIARIO**: Ingresos abiertos usados en la página diaria, con valor VLRSERVICIO.
- **CONSOLIDADO_INGRESOS_ABIERTOS+**: Consolidado de ingresos abiertos por ASEGURADOR con valor VLRSERVICIO; el nombre de la tabla termina en el signo +.
- **CUPS**: Servicios y productos prestados por código CUPS (SERVIPSPRODUCTO) con CANTIDAD, valor VLRTOTSERV, NOMBRE_TERCERO, TERCERO, CENTROCOSTO, CLASIFICACION_SERVICIO e INCLUIRPRODUCTOS. Guarda las medidas PRECIO_VENTA y Prueba CostoUnitario.
- **COSTOS**: Costo por actividad y CUPS (CUPS, NOMBREACTIVIDAD, CUP_ACTIVIDAD, COSTOACTIVIDAD, CENTROCOSTO, TERCERO) con VLRFACTURADO, VENTA, COSTO_TTL, RENTABILIDAD, RENTABILIDAD_TOTAL, %RENT, CANTIDAD y validacion.
- **ANALISIS_RENTABILIDAD**: Venta, costo histórico y costo estimado por CUPS (ACTIVI), CENTROCOSTO y TERCERO; columnas CANT, VLRMAXCUPS, COSTOHIST, COSTOVARIACION, PERDIDA, VLRSERVICIOENORDEN, TOTAL_COSTO y RENTABILIDAD_TOTAL.
- **ACTIVIDADES**: Catálogo de CUPS con código SIPCODCUP y descripción SIPDESCUP.
- **TERCEROS**: Catálogo de terceros (aseguradores y pagadores); TERNOMCOM es el nombre comercial.
- **AcreedoresConFactura**: Lista de aseguradores con factura (nombre y oid) que se usa como segmentador y como filas en FACTURACION X EPS.
- **AREAS DE SERVICIO**: Catálogo de áreas de servicio; CLASIFICACION_SERVICIO agrupa los servicios.
- **FiltroRefacturacion**: Tabla auxiliar con la columna Modo para elegir cómo se calcula la medida Refacturación Dinámica. Valores y lógica por confirmar.
- **CALENDARIO**: Tabla de fechas (Date) con la jerarquía automática de año y mes; guarda la mayoría de las medidas del tablero.
- **Origen de los datos**: El .pbix proviene del servicio Power BI y no trae consultas ni SQL legibles; el sistema de origen y el modo de almacenamiento de cada tabla están por confirmar.

## Definiciones
- **Facturación**: Valor facturado en pesos; suma de TOTALAREASERVORDEN de FACTURACION o de FACTU_AREA según el visual.
- **Devoluciones**: Valor en pesos de facturas devueltas para refacturar; suma de REFACTURACION[VLRAREASERVICIO]. Los botones y títulos dicen DEVOLUCIONES y las páginas REFACTURACION.
- **Facturación neta**: Facturación menos devoluciones, según cómo se presentan las tablas; medidas NETA, NETA_AREA, FACTURACION_NETA y Facturacion_net. Cálculo exacto por confirmar.
- **Ingresos abiertos**: Valor en pesos de servicios de ingresos (admisiones) que aún no se han facturado; también se llama facturación pendiente. Definición exacta por confirmar.
- **Asegurador**: Entidad que paga (EPS u otro tercero); según la página se titula ASEGURADOR, ASEGURADORA, PAGADOR, ENTIDAD o TERCERO.
- **Servicio**: Agrupación CLASIFICACION_SERVICIO del área de servicio; en la página diaria se titula CENTRO COSTOS.
- **CUPS**: Código Único de Procedimientos en Salud del servicio o producto prestado.
- **Frecuencia**: Cantidad de servicios o procedimientos (suma de CANTIDAD o CANT), en unidades.
- **Rentabilidad**: Venta menos costo, en pesos; el porcentaje de rentabilidad la compara con la venta. Cálculo exacto por confirmar.
- **Mes anterior**: Filtro de fecha relativa sobre CALENDARIO[Date] que deja solo el mes calendario anterior al día de consulta.
- **Participación**: Porcentaje de un valor sobre el total del visual o de su columna; es un cálculo del visual («mostrar valor como»), no una medida del modelo.

## Reglas de negocio
- **Navegación**: Todas las páginas salvo INICIO están ocultas en la barra de páginas; se abren con botones y cada una tiene arriba a la izquierda un botón con imagen que vuelve a INICIO (COMPARATIVO no lo tiene).
- **Año 2023 excluido**: Varios segmentadores de año ocultan 2023 y las matrices de facturación por servicio y por EPS filtran año distinto de 2023.
- **Costos desde septiembre de 2024**: COSTOS X MESES, Duplicado de Duplicado de COSTOS X MESES y COSTOS ANTERIOR filtran CALENDARIO[Date] mayor o igual al 1 de septiembre de 2024.
- **Unidades de los valores**: Las tarjetas muestran el valor completo en pesos sin decimales; las tortas, líneas y áreas muestran etiquetas en millones, salvo en CUPS.
- **Formato condicional**: El tablero no tiene semáforos; solo hay barras de datos (verde si es positivo, rojo si es negativo) en las tablas de rentabilidad de las páginas de costos.

## Observaciones
- **Páginas sin acceso**: COMPARATIVO, FACTURACIÓN GENERAL (solo se abre desde COMPARATIVO), Duplicado de FACTURACIÓN GENERAL, COSTOS X MESES, Duplicado de Duplicado de COSTOS X MESES y COSTOS ANTERIOR no se alcanzan desde INICIO. Por confirmar si se deben eliminar.
- **Página de facturación en uso**: El botón FACTURACIÓN de INICIO abre «Duplicado de Duplicado de FACTURACIÓN GENERAL», no FACTURACIÓN GENERAL.
- **Sin DAX disponible**: El .pbix no trae el modelo en texto (TMDL); el cálculo de todas las medidas está por confirmar.
- **Cuatro medidas de facturación neta**: NETA, NETA_AREA, FACTURACION_NETA y Facturacion_net parecen medir lo mismo. Por confirmar si dan el mismo resultado.
- **Medidas en CALENDARIO**: La mayoría de las medidas están guardadas en la tabla de fechas, no en la tabla de hechos que usan.
- **Visuales personalizados sin uso**: El informe registra tres visuales personalizados (entre ellos Power KPI Matrix y Table Grid) que ninguna página usa.
- **Sin documentación del propietario**: Todo lo descrito se infiere del informe; los puntos marcados por confirmar deben validarse con el área financiera.

## Historial de cambios
- **2026-10-20 · v1**: Documentación inicial generada a partir del informe (.pbix), sin documentación previa del propietario.
