"""
Genera tests/real/banco_holdout.json: banco HOLDOUT, independiente de
banco_real.json (que se usó para corregir el bot). Mide si las mejoras
generalizan: preguntas nuevas (ni repetidas ni paráfrasis cercanas), escritas
como las haría un usuario administrativo, con lenguaje informal y errores de
tipeo, sobre 15 tableros (incluye NAOS, CVC, RECEPCIÓN TÉCNICA, REFERENCIA y
PERFIL DE MORBILIDAD, que el banco real no cubre).

Mismo formato y mismo criterio que build_banco.py (tests/real/RETOMAR.md):
la verdad es la cifra que el usuario ve en el tablero = medida del visual +
filtros de informe, página y visual (PBIR de tableros/, vía tests/real/pbir.py)
+ periodo pedido. Los DAX se escribieron con la metadata del modelo
(data/model_metadata) y el PBIR, SIN consultar Power BI: el coordinador los
ejecuta.

    python -X utf8 -m tests.real.build_holdout            # arma el JSON
    python -X utf8 -m tests.real.correr_todo --banco tests/real/banco_holdout.json

Tipos: numero, comparacion, agrupado (incluye top N), lista, definicion y
fuera_alcance (debe rechazarse; ver run_banco.evaluate).
"""
import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.real import env as real_env  # noqa: E402
from tests.real.build_banco import (  # noqa: E402
    ANTI, ATEN, BRIEF, CITAS, DEM, EPS, FACT, FARM, LAV, TIEMPOS, agrupado, calc, case, ctx, numero)

HERE = Path(__file__).resolve().parent
BANCO = HERE / "banco_holdout.json"

NAOS = ("TABLERO NAOS", "TABLERO NAOS")
RT = ("TABLERO RECEPCION TECNICA", "TABLERO RECEPCION TECNICA")
REF = ("TABLERO_REFERENCIA", "TABLERO_REFERENCIA")
CVC = ("TABLERO_CVC", "TABLERO_CVC")
MORB = ("TABLERO PERFIL DE MORBILIDAD", "TABLERO PERFIL DE MORBILIDAD")

# Meses y años concretos (literales: la pregunta nombra el mes o el año).
SEP = ("DATE(2026, 9, 1)", "DATE(2026, 9, 30)")
AGO = ("DATE(2026, 8, 1)", "DATE(2026, 8, 31)")
A2025 = ("DATE(2025, 1, 1)", "DATE(2025, 12, 31)")
SEMANA = ("{INI_SEMANA}", "{HOY}")

SIN_PBIR = (" El PBIR local de este informe no trae la definición de los visuales (carpetas vacías): la medida "
            "sale de la documentación del tablero y del modelo; filtros de página sí tomados del PBIR.")


def rango(col, ini_fin):
    ini, fin = ini_fin
    return f"KEEPFILTERS(FILTER(ALL({col}), {col} >= {ini} && {col} <= {fin}))"


def comparacion(expr, filtros_por_clave):
    parts = [f'"{k}", ' + calc(expr, f) for k, f in filtros_por_clave.items()]
    return "EVALUATE ROW(" + ", ".join(parts) + ")"


def build():
    real_env.setup_env()
    cases = []
    add = cases.append

    # ------------------------------------------------------------ BRIEFING
    R = BRIEF[1]
    v = "d76b7140e006cec53960"
    f, s = ctx(R, "GESTIÓN CAMAS", v)
    add(case("H01", BRIEF, "numero", "cuantas camas hay en transicion ahorita?", page="GESTIÓN CAMAS", visual=v,
             skipped=s, dax=numero("DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO])", f), tol=0.0))
    v = "1d5477cb3d7ad9d21a8e"
    f, s = ctx(R, "GESTIÓN CAMAS", v)
    add(case("H02", BRIEF, "agrupado", "como estan repartidas las camas x estado", page="GESTIÓN CAMAS", visual=v,
             skipped=s, dax=agrupado("'CAMAS DISPONIBLES'[ESTADOS_CAM]",
                                     "DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO])", f), tol=0.0, top_keys=4,
             nota="Gráfico de anillos de camas por estado de GESTIÓN CAMAS."))
    v = "b9471357da411b61a93b"
    f, s = ctx(R, "DETALLE MEDICAMENTOS DESABASTECIDOS", v)
    add(case("H03", BRIEF, "numero", "cuantos medicamentos desabastesidos hay reportados",
             page="DETALLE MEDICAMENTOS DESABASTECIDOS", visual=v, skipped=s,
             dax=numero("DISTINCTCOUNT('MEDICAMENTOS DESABASTECIDOS'[OID_SOLICITUD])", f), tol=0.0))
    v = "e8f948534b605d467467"
    f, s = ctx(R, "CONSULTAS PROXIMA SEMANA", v)
    add(case("H04", BRIEF, "numero", "cuantas consultas ambulatorias hay agendadas pa la proxima semana",
             page="CONSULTAS PROXIMA SEMANA", visual=v, skipped=s,
             dax=numero("DISTINCTCOUNT(AMBULATORIO_SS[CITA])", f), tol=0.0,
             nota="Tarjeta de consultas ambulatorias (TIPO_CONSULTA = CONSULTA AMBULATORIA); la tabla trae la "
                  "semana siguiente."))
    v = "2ed97a310c3ae03ccb64"
    f, s = ctx(R, "URGENCIAS", v)
    add(case("H05", BRIEF, "numero", "triages obstetricos q van hoy en urgencias", page="URGENCIAS", visual=v,
             skipped=s, dax=numero("DISTINCTCOUNT(TRIAGES[OID_TRIAGE])", f), tol=0.0))
    v = "5e7d29a53e4547905c70"
    f, s = ctx(R, "EGRESOS PROBABLES", v)
    add(case("H06", BRIEF, "agrupado", "dame el top 3 de servicios con mas egresos probables",
             page="EGRESOS PROBABLES", visual=v, skipped=s,
             dax=agrupado("'EGRESOS PROBABLES'[HSUNOMBRE]", "DISTINCTCOUNT('EGRESOS PROBABLES'[AINCONSEC])", f,
                          top=3), tol=0.0, top_keys=3))

    # ------------------------------------------------------------ TIEMPOS URGENCIAS
    R = TIEMPOS[1]
    CAL = "Calendario[FECHA]"
    v = "9a6006e9bf111f860603"
    f, s = ctx(R, "RESUMEN", v, "este_mes", CAL)
    add(case("H07", TIEMPOS, "numero", "cuanto se demora la admision en urgencias este mes en promedio?",
             page="RESUMEN", visual=v, skipped=s, dax=numero("AVERAGE(CONSULTA_URGENCIAS[MINUTOS_ADMISION])", f),
             unidad="min", nota="Tarjeta TIEMPO ENTRE TRIAGE Y ADMISIÓN (minutos)."))
    v = "53a880b686bdf72bb412"
    f, s = ctx(R, "IMAGENES", v, extra=[rango(CAL, SEP)])
    add(case("H08", TIEMPOS, "numero", "tiempo de respuesta de imagenes en urgencias en septiembre", page="IMAGENES",
             visual=v, skipped=s, dax=numero("AVERAGE(IMAGENES[tiempo_respuesta])", f), unidad="min",
             nota="IMAGENES[tiempo_respuesta] está en minutos (diccionario)."))
    v = "e3b97507960196be77ff"
    f, s = ctx(R, "MAPA DE CALOR TRIAGE", v, "mes_pasado", CAL)
    add(case("H09", TIEMPOS, "agrupado", "promedio de triage por dia de la semana del mes pasado",
             page="MAPA DE CALOR TRIAGE", visual=v, skipped=s,
             dax=agrupado("OPORTUNIDAD_TRIAGE[DIA_SEMANA]", "AVERAGE(OPORTUNIDAD_TRIAGE[MIN])", f), unidad="min",
             tol=0.03, top_keys=7,
             nota="Mapa de calor de triage (columnas = día de la semana), sin desagregar por tramo horario."))
    v = "f17cf6e592d61eabecb9"
    f, s = ctx(R, "RESUMEN", v, "este_ano", CAL)
    add(case("H10", TIEMPOS, "numero",
             "en lo q va del año cuanto tiempo pasa un paciente en urgencias hasta que lo suben a hospitalizacion",
             page="RESUMEN", visual=v, skipped=s, dax=numero("AVERAGE(TIEMPO_HOSPI[TIEMPO_HOSPI])", f), unidad="h",
             tol=0.03, nota="Tarjeta TIEMPO PROMEDIO EN URGENCIAS (HOSPITALIZACIÓN); TIEMPO_HOSPI en horas."))
    v = "8713e601ba911d07552d"
    fa, s = ctx(R, "TIEMPO EGRESO", v, extra=[rango(CAL, AGO)])
    fs, _ = ctx(R, "TIEMPO EGRESO", v, extra=[rango(CAL, SEP)])
    add(case("H11", TIEMPOS, "comparacion", "como estuvo el tiempo pa egreso de urgencias en agosto comparado con septiembre",
             page="TIEMPO EGRESO", visual=v, skipped=s, unidad="min",
             dax=comparacion("AVERAGE(TIEMPO_PARA_EGRESO[TIEMPO_EGRESO_OK])", {"agosto": fa, "septiembre": fs})))

    # ------------------------------------------------------------ ATENCIONES INSTITUCIONALES
    R = ATEN[1]
    CAL = "'Calendario'[Date]"
    f, s = ctx(R, "HOSPITALIZACION PARCIAL", None, extra=[rango(CAL, A2025)])
    add(case("H12", ATEN, "numero", "cuantas atenciones de hospitalizacion parcial hubo en 2025",
             page="HOSPITALIZACION PARCIAL", skipped=s, dax=numero("[ATENCION_HP]", f), tol=0.01))
    f, s = ctx(R, "ABORTOS", None, "este_ano", CAL)
    add(case("H13", ATEN, "numero", "cuantos abortos van este año", page="ABORTOS", skipped=s,
             dax=numero("COUNTROWS(PARTOS_DRIVE)", f), tol=0.01,
             nota="Página ABORTOS (Tipo de parto ABORTO o IVE), mismo conteo que la página PARTOS. El filtro de "
                  "página no traducido es FECHA_REAL > 2024-01-01: no cambia «este año»."))
    f, s = ctx(R, "CONSULTAS AMBULATORIAS", None, "mes_pasado", CAL)
    add(case("H14", ATEN, "numero", "las consultas ambulatorias del mes pasado cuantas fueron?",
             page="CONSULTAS AMBULATORIAS", skipped=s, dax=numero("[Total Consultas]", f), tol=0.01))
    f, s = ctx(R, "CONSULTAS AMBULATORIAS", None, "este_ano", CAL)
    add(case("H15", ATEN, "agrupado", "las 5 especialidades con mas consultas ambulatorias este año",
             page="CONSULTAS AMBULATORIAS", skipped=s,
             dax=agrupado("CONSULTAS_AMBULATORIAS[ESPECIALIDAD]", "[Total Consultas]", f, top=5), tol=0.01))

    # ------------------------------------------------------------ ASIGNACION DE CITAS
    R = CITAS[1]
    v = "984ade5225e54a5a0361"
    f, s = ctx(R, "OFERTA ESPECIALIDADES", v)
    add(case("H16", CITAS, "numero", "que porcentaje de citas estan pendientes", page="OFERTA ESPECIALIDADES",
             visual=v, skipped=s, dax=numero("[%PENDIENTE]", f), unidad="%", porcentaje=True,
             nota="[%PENDIENTE] = solicitudes en espera / citas asignadas; puede pasar de 100 %."))
    v = "1552eb3df989fe3f0cb2"
    f, s = ctx(R, "EN ESPERA X ESPECIALIDAD", v)
    add(case("H17", CITAS, "agrupado", "top 5 aseguradoras con mas citas en espera", page="EN ESPERA X ESPECIALIDAD",
             visual=v, skipped=s, dax=agrupado("ASEGURADORA[ASEGURADORA_HM]", "COUNT(EN_ESPERA[OID_CITA])", f, top=5),
             tol=0.0,
             nota="Gráfico TOP 5 ASEGURADORAS CON CITAS EN ESPERA (el filtro TopN del visual, no traducido, es "
                  "el TOPN 5 del DAX)."))
    add(case("H18", CITAS, "definicion", "el % pendiente de citas como lo calculan? puede dar mas de 100?",
             esperado={"todas": ["asignad"], "alguna": ["espera", "pendiente"]},
             fuente="docs_tableros/tablero_asignacion_de_citas/md/_diccionario.md"))

    # ------------------------------------------------------------ EPS
    R = EPS[1]
    v = "225bbdb8e1ccc7a86b3a"
    f, s = ctx(R, "CONSULTAS PRIORITARIAS", v)
    add(case("H19", EPS, "agrupado", "consultas prioritarias por estado en el tablero eps", page="CONSULTAS PRIORITARIAS",
             visual=v, skipped=s, dax=agrupado("CONSULTAS_PRIORITARIAS[ESTADO_NOMBRE]",
                                               "COUNT(CONSULTAS_PRIORITARIAS[ESTADO_NOMBRE])", f), tol=0.0, top_keys=4))
    v = "23d6444370810778f0bb"
    f, s = ctx(R, "TRIAGES ATENDIDOS", v)
    add(case("H20", EPS, "numero", "cuantos triages obstetricos atendidos muestra eps", page="TRIAGES ATENDIDOS",
             visual=v, skipped=s, dax=numero("COUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE])", f), tol=0.0))

    # ------------------------------------------------------------ FARMACIA
    R = FARM[1]
    v = "878ef1301da929a65e21"
    f, s = ctx(R, "MEDICAMENTOS VENCIDOS", v)
    add(case("H21", FARM, "numero", "cuantos productos se vencen entre 2 y 4 meses", page="MEDICAMENTOS VENCIDOS",
             visual=v, skipped=s, dax=numero("DISTINCTCOUNT(VENCIMIENTO_PRODUCTOS[IPRCODIGO])", f), tol=0.0))
    v = "e8ef2e93c24e94fd4b29"
    f, s = ctx(R, "INICIO", v)
    add(case("H22", FARM, "agrupado", "pendientes de farmacia por rango de horas", page="INICIO", visual=v, skipped=s,
             dax=agrupado("PENDIENTES_FARMACIA[HORAS_SUMINISTRO]", "DISTINCTCOUNT(PENDIENTES_FARMACIA[HCNFOLIO])", f),
             tol=0.0, top_keys=6))

    # ------------------------------------------------------------ FACTURACIÓN
    R = FACT[1]
    v = "660c059b754b0090691c"
    f, s = ctx(R, "RADICACION DE CUENTAS", v)
    add(case("H23", FACT, "numero", "cuanto se demoran en radicacion de cuentas en promedio", page="RADICACION DE CUENTAS",
             visual=v, skipped=s, dax=numero("AVERAGE('FACTURACION PERFILES'[TIEMPO])", f), tol=0.02))
    v = "17425c6871d3e5657b58"
    f, s = ctx(R, "INICIO", v)
    add(case("H24", FACT, "agrupado", "valor estimado x area de servicio", page="INICIO", visual=v, skipped=s,
             dax=agrupado("ULT_GESTION[AREA_SERVICIO]", "SUM(ULT_GESTION[FACTURADO])", f, top=10), unidad="$",
             tol=0.01, nota="Barras VALOR ESTIMADO POR SERVICIO (sin desagregar la serie TIPO_INGRESO)."))
    v = "1b789e9af83a2e0c4f68"
    f, s = ctx(R, "FACTURACION PENDIENTE", v)
    add(case("H25", FACT, "numero", "cuantos ingresos hospitalarios estan pendientes por facturar",
             page="FACTURACION PENDIENTE", visual=v, skipped=s,
             dax=numero("DISTINCTCOUNT(PENDIENTES_FACTURACION[INGRESO])", f), tol=0.0))

    # ------------------------------------------------------------ DEMANDA INSATISFECHA
    R = DEM[1]
    CAL = "CALENDARIO[Date]"
    v = "500f2dbca7445d1567d6"
    f, s = ctx(R, "REFERENCIA", v, "este_ano", CAL)
    add(case("H26", DEM, "numero", "cuantas remisiones no pudimos recibir este año", page="REFERENCIA", visual=v,
             skipped=s, dax=numero("DISTINCTCOUNT(REFERENCIA[OID])", f), tol=0.0,
             nota="Demanda insatisfecha por referencia (causas de la institución). El TABLERO REFERENCIA solo "
                  "trae 30 días: no responde «este año»."))
    v = "0dd5b6bdac1e3cc01ca0"
    f, s = ctx(R, "CIRUGÍAS", v, "mes_pasado", CAL)
    add(case("H27", DEM, "numero", "cirugias canceladas el mes pasado x demanda insatisfecha", page="CIRUGÍAS",
             visual=v, skipped=s, dax=numero("COUNT('CIRUGÍAS'[PROCEDIMIENTO])", f), tol=0.0))
    fa, _ = ctx(R, "CIRUGÍAS", v, extra=[rango(CAL, AGO)])
    fs, _ = ctx(R, "CIRUGÍAS", v, extra=[rango(CAL, SEP)])
    add(case("H27b", DEM, "comparacion", "cirujias canceladas en agosto vs septiembre, cual mes tuvo mas?",
             page="CIRUGÍAS", visual=v, skipped=s,
             dax=comparacion("COUNT('CIRUGÍAS'[PROCEDIMIENTO])", {"agosto": fa, "septiembre": fs})))
    v = "b18910ca086d0609e975"
    f, s = ctx(R, "CITAS", v, "este_ano", CAL)
    add(case("H28", DEM, "agrupado", "por que motivos cancelo citas la institucion este año?", page="CITAS",
             visual=v, skipped=s, dax=agrupado("'CITAS MEDICAS'[CCCDESCRI]", "DISTINCTCOUNT('CITAS MEDICAS'[OID])", f),
             tol=0.0, top_keys=3))

    # ------------------------------------------------------------ ANTIBIÓTICOS
    add(case("H29", ANTI, "lista", "q antibioticos se estan usando ahorita", page="MONITOREO_ANTIBIOTICO",
             dax="EVALUATE FILTER(VALUES(ANTIBIOTICOS[ANTIBIOTICO]), [PAC_ACT] > 0)", cobertura=0.6,
             nota="Eje del gráfico PACIENTES ACTIVOS POR TIPO DE ANTIBIÓTICO (antibióticos con pacientes activos).",
             criterio="Lista de antibióticos con [PAC_ACT] > 0: las barras del gráfico PACIENTES ACTIVOS POR TIPO DE "
                      "ANTIBIÓTICO de MONITOREO_ANTIBIOTICO (sin filtros de página ni de visual)."))
    add(case("H30", ANTI, "definicion", "como cuentan los pacientes activos con antibiotico?",
             esperado={"todas": ["activo"], "alguna": ["despach", "aplica", "documento", "distint", "farmacia"]},
             fuente="docs_tableros/tablero_antibioticos/md/_diccionario.md"))

    # ------------------------------------------------------------ LAVANDERÍA
    R = LAV[1]
    f, s = ctx(R, "Página 1", None, extra=[rango("LAVANDERIA[Fecha]", SEP)])
    f2, _ = ctx(R, "Página 1", None, extra=[rango("LAVANDERIA[FechaRegistro]", SEP)])
    add(case("H31", LAV, "numero", "kilos d ropa lavados en septiembre", page="Página 1", skipped=s,
             dax=numero("SUM(LAVANDERIA[Peso])", f), unidad="kg", tol=0.01,
             alternativas=[numero("SUM(LAVANDERIA[Peso])", f2)],
             nota="Mismo criterio que LV01: se acepta Fecha o FechaRegistro."))
    f, s = ctx(R, "Página 1", None, extra=[rango("LAVANDERIA[Fecha]", SEMANA)])
    f2, _ = ctx(R, "Página 1", None, extra=[rango("LAVANDERIA[FechaRegistro]", SEMANA)])
    add(case("H32", LAV, "numero", "cuanta ropa se ha lavado esta semana", page="Página 1", skipped=s,
             dax=numero("SUM(LAVANDERIA[Peso])", f), unidad="kg", tol=0.01,
             alternativas=[numero("SUM(LAVANDERIA[Peso])", f2)],
             nota="Semana = del lunes de esta semana a hoy ({INI_SEMANA}..{HOY}); Fecha o FechaRegistro."))

    # ------------------------------------------------------------ NAOS
    R = NAOS[1]
    v = "79ae233890566352860c"
    f, s = ctx(R, "LISTADO", v)
    add(case("H33", NAOS, "numero", "cuantos pacientes naos tenemos con pendientes?", page="LISTADO", visual=v,
             skipped=s, dax=numero("DISTINCTCOUNT(PACIENTES[AINCONSEC])", f), tol=0.0,
             nota="Tarjeta PACIENTES de LISTADO (Count distinct de AINCONSEC; el queryRef dice Sum pero la función "
                  "de agregación del PBIR es 2 = recuento distinto)."))
    v = "31e76a8384c5af1fdc26"
    f, s = ctx(R, "CIRUGÍAS PENDIENTES", v)
    add(case("H34", NAOS, "numero", "cirugias pendientes de los pacientes de naos", page="CIRUGÍAS PENDIENTES",
             visual=v, skipped=s, dax=numero("DISTINCTCOUNT('CIRUGÍAS PENDIENTES'[oid])", f), tol=0.0,
             contrapregunta_ok=True, elegir="NAOS",
             nota="La página PENDIENTES de Atenciones también cuenta cirugías pendientes (otra población)."))
    v = "bbc1080129686aebc6da"
    f, s = ctx(R, "LISTADO", v)
    add(case("H35", NAOS, "agrupado", "pacientes naos x tipo de paciente", page="LISTADO", visual=v, skipped=s,
             dax=agrupado("PACIENTES[TIPO_PACIENTE]", "DISTINCTCOUNT(PACIENTES[ADNINGRESO])", f), tol=0.0,
             top_keys=4))

    # ------------------------------------------------------------ RECEPCIÓN TÉCNICA
    R = RT[1]
    v = "0000b124aadde65385e8"
    f, s = ctx(R, "INGRESOS DÍA", v)
    add(case("H36", RT, "numero", "cuantos pedidos estan en gestion hoy en recepcion tecnica", page="INGRESOS DÍA",
             visual=v, skipped=s, dax=numero("DISTINCTCOUNT(TablaPedidosActuales[OidRTPedido])", f), tol=0.0))
    v = "1c5a5f0f71da8940b500"
    f, s = ctx(R, "CANTIDADES", v)
    add(case("H37", RT, "agrupado", "solicitudes pendientes de recepcion tecnica por area de servicio",
             page="CANTIDADES", visual=v, skipped=s,
             dax=agrupado("PENDIENTES_RT[GASNOMBRE]", "DISTINCTCOUNT(PENDIENTES_RT[OID])", f, top=10), tol=0.0,
             nota="DirectQuery en vivo: la verdad se calcula en el mismo momento que la respuesta."))
    add(case("H38", RT, "definicion", "por q estados pasa un pedido en recepcion tecnica?",
             esperado={"todas": ["recepcion"], "alguna": ["transportadora", "almacenada", "registro sanitario",
                                                          "administrativa"]},
             fuente="docs_tableros/tablero_recepcion_tecnica/md/_diccionario.md"))

    # ------------------------------------------------------------ REFERENCIA
    R = REF[1]
    f, s = ctx(R, "INICIO")
    add(case("H39", REF, "numero", "cuantas solicitudes de referencia nos llegaron en el ultimo mes", page="INICIO",
             skipped=s, dax=numero("DISTINCTCOUNT(REFERENCIA[OID])", f), tol=0.0,
             alternativas=[numero("COUNTROWS(REFERENCIA)", f)],
             criterio="Tarjeta CANTIDAD DE SOLICITUDES de INICIO: REFERENCIA trae las solicitudes con llamada de los "
                      "últimos 30 días (= «último mes»). Medida por confirmar: conteo distinto de OID o filas."
                      + SIN_PBIR))
    f, s = ctx(R, "DETALLE NO ACEPTADOS RECEPCION")
    add(case("H40", REF, "numero", "y cuantas de esas referencias no aceptamos?", page="DETALLE NO ACEPTADOS RECEPCION",
             skipped=s, dax=numero("DISTINCTCOUNT(REFERENCIA[OID])", f), tol=0.0, contrapregunta_ok=True,
             elegir="REFERENCIA",
             criterio="Tarjeta de solicitudes de DETALLE NO ACEPTADOS RECEPCION (filtro de página ESTADO = No "
                      "Aceptado), últimos 30 días. Contrapregunta legítima: Demanda Insatisfecha también cuenta "
                      "referencias no aceptadas (otro filtro de causas y otro periodo)." + SIN_PBIR))
    f, s = ctx(R, "INICIO")
    add(case("H41", REF, "agrupado", "top 5 especialidades q mas piden referencia", page="INICIO", skipped=s,
             dax=agrupado("REFERENCIA[GEEDESCRI]", "DISTINCTCOUNT(REFERENCIA[OID])", f, top=6), tol=0.0, top_keys=5,
             criterio="Tabla ESPECIALIDAD / SOLICITUDES de INICIO (últimos 30 días). TOPN 6 porque la fila sin "
                      "especialidad suele ser la mayor y el comparador ignora claves vacías." + SIN_PBIR))
    add(case("H42", REF, "definicion", "como se calcula el tiempo de respuesta en referencia?",
             esperado={"todas": ["llamada"], "alguna": ["acept", "horas"]},
             fuente="docs_tableros/tablero_referencia/md/_diccionario.md"))

    # ------------------------------------------------------------ CVC
    R = CVC[1]
    f, s = ctx(R, "CVC", None, "este_ano", "'calendario'[Date]")
    add(case("H43", CVC, "agrupado", "cuantas compras subieron, bajaron o se quedaron igual de precio este año",
             page="CVC", skipped=s, dax=agrupado("COSTOS_PRODUCTOS[ESTADO]", "COUNTROWS(COSTOS_PRODUCTOS)", f),
             tol=0.0, top_keys=3,
             criterio="Torta «Volatilidad de Costos por Mes y Año» de CVC: número de registros AUMENTÓ, ESTABLE y "
                      "DISMINUYÓ (cvc.md) + año en curso por 'calendario'[Date]." + SIN_PBIR))
    add(case("H44", CVC, "definicion", "en cvc cuando un producto sale como AUMENTÓ q significa",
             esperado={"todas": ["aument"], "alguna": ["anterior"]},
             fuente="docs_tableros/tablero_cvc/md/cvc.md"))

    # ------------------------------------------------------------ PERFIL DE MORBILIDAD
    R = MORB[1]
    f, s = ctx(R, "PERFIL DE MORBILIDAD", None, extra=[rango("'Calendario'[Date]", A2025)])
    add(case("H45", MORB, "numero", "cual fue el porcentaje de mortalidad en 2025 segun el perfil de morbilidad",
             page="PERFIL DE MORBILIDAD", skipped=s, dax=numero("[%DEFUNCIONES]", f), unidad="%", porcentaje=True,
             tol=0.02,
             criterio="Total de %DEFUNCIONES de PERFIL DE MORBILIDAD con el año 2025 ('Calendario'[Date] → "
                      "MATRIZ 2024[fecha])." + SIN_PBIR))
    add(case("H46", MORB, "definicion", "q es el % de defunciones del perfil de morbilidad y como lo sacan",
             esperado={"todas": ["defunci"], "alguna": ["cie10", "cie 10", "cie-10", "egreso"]},
             fuente="docs_tableros/tablero_perfil_de_morbilidad/md/_diccionario.md"))

    # ------------------------------------------------------------ FUERA DE ALCANCE
    rechazo = {"rechazo": True}
    crit = "Fuera de alcance: debe rechazarse sin consultar Power BI y sin inventar cifras."
    add(case("H47", BRIEF, "fuera_alcance", "oye y cuanto esta el dolar hoy?", esperado=rechazo, criterio=crit))
    add(case("H48", BRIEF, "fuera_alcance", "me ayudas a escribir un mensaje de feliz cumpleaños pa mi jefa",
             esperado=rechazo, criterio=crit))
    add(case("H49", ANTI, "fuera_alcance", "cual es el mejor antibiotico pa una infeccion de garganta?",
             esperado=rechazo,
             criterio=crit + " Es consejo clínico, no administrativo, aunque nombre un tablero (antibióticos)."))
    return cases


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.parse_args(argv)
    cases = build()
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "ids repetidos"
    BANCO.write_text(json.dumps({"version": 1, "holdout": True, "casos": cases}, ensure_ascii=False, indent=1,
                                default=str), encoding="utf-8")
    print(f"{len(cases)} casos -> {BANCO}")


if __name__ == "__main__":
    main()
