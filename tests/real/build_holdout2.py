"""
Genera tests/real/banco_holdout2.json: SEGUNDO banco holdout (50 preguntas).

Escrito como lo preguntaría un usuario administrativo NUEVO, sin mirar el
código de src/ ni las fallas de las corridas anteriores, con la misma mezcla
de tableros y tipos que banco_holdout.json (15 tableros documentados,
lenguaje informal y algún error de tipeo). No repite ni parafrasea preguntas
de los otros bancos: tests/real/similitud.py lo verifica (y la prueba
tests.real.test_bancos lo exige).

Mismo criterio de verdad que build_banco.py (tests/real/RETOMAR.md): la cifra
que el usuario ve en el tablero = medida del visual + filtros de informe,
página y visual (PBIR de tableros/, vía tests/real/pbir.py) + periodo pedido.
Para los PBIP locales incompletos (REFERENCIA, CVC, MORBILIDAD y las páginas
de ATENCIONES sin visuales) la verdad sale del modelo (data/model_metadata) y
de la documentación (docs_tableros/); el campo «criterio» lo dice.

    python -X utf8 -m tests.real.build_holdout2
    python -X utf8 -m tests.real.correr_todo --banco tests/real/banco_holdout2.json
"""
import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.real import env as real_env  # noqa: E402
from tests.real.build_banco import (  # noqa: E402
    ANTI, ATEN, BRIEF, CITAS, DEM, EPS, FACT, FARM, LAV, TIEMPOS, agrupado, case, ctx, find_visual, numero)
from tests.real.build_holdout import CVC, MORB, NAOS, REF, RT, comparacion, rango  # noqa: E402

HERE = Path(__file__).resolve().parent
BANCO = HERE / "banco_holdout2.json"

# Meses concretos (la pregunta nombra el mes; hoy es noviembre de 2026).
JUN = ("DATE(2026, 6, 1)", "DATE(2026, 6, 30)")
JUL = ("DATE(2026, 7, 1)", "DATE(2026, 7, 31)")
AGO = ("DATE(2026, 8, 1)", "DATE(2026, 8, 31)")
SEP = ("DATE(2026, 9, 1)", "DATE(2026, 9, 30)")
OCT = ("DATE(2026, 10, 1)", "DATE(2026, 10, 31)")
A2025 = ("DATE(2025, 1, 1)", "DATE(2025, 12, 31)")
SEMANA_PASADA = ("{INI_SEMANA_PASADA}", "{FIN_SEMANA_PASADA}")

MODELO_DOC = (" PBIP local incompleto: la medida y los filtros salen del modelo (data/model_metadata) y de la "
              "documentación del tablero (docs_tableros/), no de un visual del PBIR.")
PARTOS_FECHA = (" El filtro de página de PARTOS sobre 'Calendario'[Date] no se traduce (lado derecho no literal, "
                "igual que AI06/H13) y no cambia el año pedido.")


def contiene(col, texto):
    return f'KEEPFILTERS(FILTER(ALL({col}), CONTAINSSTRING({col}, "{texto}")))'


def igual(col, valor):
    return f'KEEPFILTERS(FILTER(ALL({col}), {col} = "{valor}"))'


def build():
    real_env.setup_env()
    cases = []
    add = cases.append

    # ------------------------------------------------------------ BRIEFING (7)
    R = BRIEF[1]
    v = "4a7d0e7f62fabed11f55"
    f, s = ctx(R, "CONVENIOS", v, extra=[igual("CONVENIOS[FILTRO_VIG]", "VIGENTE")])
    add(case("G01", BRIEF, "numero", "con cuantas entidades tenemos convenio vigente?", page="CONVENIOS", visual=v,
             skipped=s, dax=numero("COUNT(CONVENIOS[ENTIDAD ])", f), tol=0.0,
             nota="Porción VIGENTE de la dona CANTIDAD DE CONTRATOS POR VIGENCIA (CountNonNull de ENTIDAD)."))
    v = "c9201dbba554d1531d27"
    f, s = ctx(R, "DETALLE OCUPACIÓN", v)
    add(case("G02", BRIEF, "agrupado", "en q pisos o servicios estan repartidos los pacientes internados",
             page="DETALLE OCUPACIÓN", visual=v, skipped=s,
             dax=agrupado("'PACIENTES X ASEGURADORA'[HSUNOMBRE]",
                          "DISTINCTCOUNT('PACIENTES X ASEGURADORA'[ADNINGRESO])", f), tol=0.0))
    v = "6b0bd9028ac5f7feb43f"
    f, s = ctx(R, "EGRESOS PROBABLES", v)
    add(case("G03", BRIEF, "numero", "de las altas que se esperaban hoy cuantas ya se hicieron efectivas",
             page="EGRESOS PROBABLES", visual=v, skipped=s,
             dax=numero("SUM('EGRESOS PROBABLES'[EGRESO_EFECTIVO_HOY])", f), tol=0.0))
    v = "3d1795f9a46904840108"
    f, s = ctx(R, "INGRESOS Y EGRESOS", v)
    add(case("G04", BRIEF, "numero", "el dia de ayer cuantos pacientes nuevos se admitieron?",
             page="INGRESOS Y EGRESOS", visual=v, skipped=s, dax=numero("DISTINCTCOUNT(INGRESOS[CONSECUTIVO])", f),
             tol=0.0, nota="Tarjeta de ingresos de INGRESOS Y EGRESOS (la tabla trae el día anterior)."))
    v = "d19840f3f78032edb03a"
    f, s = ctx(R, "SOLICITUD CAMAS", v)
    add(case("G05", BRIEF, "agrupado", "que tipo de cama es la que mas estan pidiendo", page="SOLICITUD CAMAS",
             visual=v, skipped=s, dax=agrupado("'SOLICITUD CAMAS'[TIPO]", "DISTINCTCOUNT('SOLICITUD CAMAS'[oid])", f),
             tol=0.0, top_keys=1, nota="Torta SOLICITUDES POR TIPO DE CAMA."))
    v = "1d5477cb3d7ad9d21a8e"
    f, s = ctx(R, "GESTIÓN CAMAS", v, extra=[igual("'CAMAS DISPONIBLES'[ESTADOS_CAM]", "BLOQUEADA")])
    add(case("G06", BRIEF, "numero", "hay camas bloqueadas? cuantas son", page="GESTIÓN CAMAS", visual=v, skipped=s,
             dax=numero("DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO])", f), tol=0.0,
             nota="Porción BLOQUEADA de la dona de camas por estado (CountNonNull de HCACODIGO; un código por cama)."))
    v = "f24f7be74a100494959b"
    f, s = ctx(R, "IMAGENES DIAGNOSTICAS", v)
    add(case("G07", BRIEF, "agrupado", "imagenes diagnosticas tomadas segun el area que las pidio",
             page="IMAGENES DIAGNOSTICAS", visual=v, skipped=s,
             dax=agrupado("IMAGENES_TOMADAS[AREA_DE_SERVICIO]", "COUNT(IMAGENES_TOMADAS[ID_INGRESO])", f), tol=0.0,
             nota="Barras IMAGENES TOMADAS POR AREA DE SERVICIO."))

    # ------------------------------------------------------------ TIEMPOS URGENCIAS (5)
    R = TIEMPOS[1]
    CAL = "Calendario[FECHA]"
    v = "86db591799a4d36cd53b"
    f, s = ctx(R, "TIEMPO ASIGNACIÓN CAMAS", v, extra=[rango(CAL, OCT)])
    add(case("G08", TIEMPOS, "numero", "en octubre cuanto se tardaban en asignarle cama a un paciente de urgencias",
             page="TIEMPO ASIGNACIÓN CAMAS", visual=v, skipped=s,
             dax=numero("AVERAGE(TIEMPO_PARA_EGRESO[TIEMPO_ASIG_CAMA])", f), unidad="min", tol=0.03,
             nota="Línea de tiempo para asignación de cama (minutos), SUBGRUPO = URGENCIAS."))
    v = "5e969b9a581cae3334a8"
    f, s = ctx(R, "INTERCONSULTAS", v, extra=[rango(CAL, OCT)])
    add(case("G09", TIEMPOS, "numero", "numero de interconsultas respondidas en urgencias durante octubre",
             page="INTERCONSULTAS", visual=v, skipped=s, dax=numero("SUM(INTERCONSULTA[RESPUESTAS])", f), tol=0.0))
    v = "91b9e8de4c7c5c75e5a7"
    f, s = ctx(R, "INTERCONSULTAS", v, extra=[rango(CAL, SEMANA_PASADA)])
    add(case("G10", TIEMPOS, "numero", "la semana pasada urgencias pidio cuantas interconsultas?",
             page="INTERCONSULTAS", visual=v, skipped=s, dax=numero("SUM(INTERCONSULTA[SOLICITUDES])", f), tol=0.0,
             nota="Semana pasada = lunes a domingo anteriores ({INI_SEMANA_PASADA}..{FIN_SEMANA_PASADA})."))
    v = find_visual(R, "EXAMENES", "TIEMPO_RESPUESTA", "card")
    fj, s = ctx(R, "EXAMENES", v, extra=[rango(CAL, JUL)])
    fn, _ = ctx(R, "EXAMENES", v, extra=[rango(CAL, JUN)])
    add(case("G11", TIEMPOS, "comparacion", "los resultados de laboratorio de urgencias salieron mas rapido en junio o en julio?",
             page="EXAMENES", visual=v, skipped=s, unidad="min",
             dax=comparacion("AVERAGE(EXAMENES[TIEMPO_RESPUESTA])", {"junio": fn, "julio": fj})))
    add(case("G12", TIEMPOS, "definicion", "desde que momento y hasta cual se mide lo de asignacion de cama en urgencias",
             esperado={"todas": ["cama"], "alguna": ["admisi", "estancia", "ingreso"]},
             fuente="docs_tableros/tablero_tiempos_urgencias/md/tiempo_asignacion_camas.md"))

    # ------------------------------------------------------------ ATENCIONES INSTITUCIONALES (4)
    R = ATEN[1]
    CAL = "'Calendario'[Date]"
    f, s = ctx(R, "PARTOS", None, "este_ano", CAL)
    add(case("G13", ATEN, "numero", "cesareas realizadas en lo corrido del 2026", page="PARTOS", skipped=s,
             dax=numero("SUM(PARTOS_DRIVE[CESÁREAS])", f), tol=0.01,
             criterio="Suma de PARTOS_DRIVE[CESÁREAS] con el filtro de página de PARTOS (sin abortos ni IVE) y el año "
                      "en curso por 'Calendario'[Date]." + MODELO_DOC + PARTOS_FECHA))
    f, s = ctx(R, "PARTOS", None, extra=[rango(CAL, A2025)])
    add(case("G14", ATEN, "numero", "en 2025 por cada cesarea cuantos partos vaginales hubo", page="PARTOS", skipped=s,
             dax=numero("[RELACIÓN]", f), tol=0.02,
             criterio="[RELACIÓN] = SUM(VAGINALES)/SUM(CESÁREAS) de PARTOS_DRIVE con el filtro de página de PARTOS y "
                      "el año 2025." + MODELO_DOC + PARTOS_FECHA))
    f, s = ctx(R, "CONSULTAS OBSTETRICAS", None, extra=[rango(CAL, OCT)])
    # Auditoría holdout 2: el filtro de página del PBIR usa CONSULTA_URGENCIAS[TIPO_TRIAGE], que ya no existe en el
    # modelo (la columna es CLASIFICACION_TRIAGE) y rompía la verdad. [Total_consultas_gineco] ya se restringe a
    # «-G»/MATERNIDAD, así que se quita el filtro obsoleto.
    f = [x for x in f if "TIPO_TRIAGE" not in x]
    add(case("G15", ATEN, "numero", "consultas de urgencias de gineco obstetricia en octubre", page="CONSULTAS OBSTETRICAS",
             skipped=s, dax=numero("[Total_consultas_gineco]", f), tol=0.01,
             criterio="[Total_consultas_gineco] (clasificación con «-G» o causa MATERNIDAD) con el filtro de página de "
                      "CONSULTAS OBSTETRICAS y octubre de 2026." + MODELO_DOC))
    f, s = ctx(R, "CIRUGIAS", None, extra=[rango(CAL, SEP)])
    add(case("G16", ATEN, "agrupado", "las 5 especialidades quirurgicas que mas operaron en septiembre", page="CIRUGIAS",
             skipped=s, dax=agrupado("CIRUGIAS[ESPECIALIDAD]", "[TOTAL_CIRUGIAS]", f, top=5), tol=0.01,
             criterio="[TOTAL_CIRUGIAS] por CIRUGIAS[ESPECIALIDAD], septiembre de 2026 ('Calendario'[Date])."
                      + MODELO_DOC))

    # ------------------------------------------------------------ ASIGNACION DE CITAS (3)
    R = CITAS[1]
    v = "9e03d7b662e8502b0d3b"
    f, s = ctx(R, "INICIO", v)
    # Auditoría holdout 2 (G19): el filtro de página sobre EN_ESPERA[CCEESTADO] es de OTRA tabla y cambia la cifra
    # < 2 % (105.741 frente a 104.868); como en AC02 se acepta también la cifra sin ese filtro.
    add(case("G17", CITAS, "numero", "cuantas citas ya fueron confirmadas por el paciente", page="INICIO", visual=v,
             skipped=s, dax=numero("SUM(CITAS_ASIGNADAS[CONFIRMADO])", f), tol=0.0,
             alternativas=[numero("SUM(CITAS_ASIGNADAS[CONFIRMADO])", [])],
             nota="Porción CONFIRMADO de la torta de estados de INICIO."))
    v = "ce79a12d6b5d1b85e797"
    f, s = ctx(R, "OFERTA ESPECIALIDADES", v)
    add(case("G18", CITAS, "agrupado", "q dia de la semana es el que mas gente deja de ir a la cita",
             page="OFERTA ESPECIALIDADES", visual=v, skipped=s,
             dax=agrupado("Calendario[DIA_SEMANA]", "SUM(CITAS_ASIGNADAS[Inasistida])", f), tol=0.0, top_keys=1))
    v = "9e03d7b662e8502b0d3b"
    f, s = ctx(R, "INICIO", v)
    add(case("G19", CITAS, "numero", "total de citas anuladas", page="INICIO", visual=v, skipped=s,
             dax=numero("SUM(CITAS_ASIGNADAS[ANULADO])", f), tol=0.0,
             alternativas=[numero("SUM(CITAS_ASIGNADAS[ANULADO])", [])],
             nota="Porción ANULADO de la torta de estados de INICIO."))

    # ------------------------------------------------------------ EPS (2)
    R = EPS[1]
    v = "b64226e940cac39c861d"
    f, s = ctx(R, "TRIAGES ATENDIDOS", v)
    add(case("G20", EPS, "numero", "segun el tablero de las eps cuantos pacientes estan hospitalizados en urgencias",
             page="TRIAGES ATENDIDOS", visual=v, skipped=s,
             dax=numero("COUNT(PACIENTES_HOSPITALIZADOS[PACNUMDOC])", f), tol=0.0))
    v = "296cc058d2bb12dc6b21"
    f, s = ctx(R, "TRIAGES ATENDIDOS", v)
    add(case("G21", EPS, "numero", "en eps cuantas atenciones de urgencias hay sin contar las obstetricas",
             page="TRIAGES ATENDIDOS", visual=v, skipped=s,
             dax=numero("DISTINCTCOUNT(CONSULTA_URGENCIAS[OID_TRIAGE])", f), tol=0.0))

    # ------------------------------------------------------------ FARMACIA (2)
    R = FARM[1]
    add(case("G22", FARM, "definicion", "q quiere decir oportunidad de dispensacion en farmacia y en q unidad esta",
             esperado={"todas": ["dispensa"], "alguna": ["hora", "horas"]},
             fuente="docs_tableros/tablero_farmacia/md/oportunidad_dispensacion.md"))
    v = "d812d390d4c9c2eb2778"
    f, s = ctx(R, "INICIO", v)
    add(case("G23", FARM, "agrupado", "productos proximos a vencer agrupados por mes de vencimiento", page="INICIO",
             visual=v, skipped=s, dax=agrupado("VENCIMIENTO_PRODUCTOS[mes]", "COUNT(VENCIMIENTO_PRODUCTOS[IFICANTID])", f),
             tol=0.0, top_keys=4))

    # ------------------------------------------------------------ FACTURACIÓN (3)
    R = FACT[1]
    v = "057dda6f630cc1909072"
    f, s = ctx(R, "FACTURADORES", v)
    add(case("G24", FACT, "numero", "cuanta plata suman los montos facturados por los facturadores",
             page="FACTURADORES", visual=v, skipped=s, dax=numero("SUM(FACTURADORES[MONTO_FACTURADO])", f),
             unidad="$", tol=0.01))
    v = "69698660b478049e4780"
    f, s = ctx(R, "EN PROCESO FACTURACION", v)
    add(case("G25", FACT, "numero", "cuantos dias llevan en promedio las cuentas hospitalarias que estan en facturacion",
             page="EN PROCESO FACTURACION", visual=v, skipped=s, dax=numero("[PROMEDIO_DIAS_PROCESO]", f),
             unidad="días", tol=0.02))
    add(case("G26", FACT, "definicion", "eso de valor estimado en control de facturacion incluye cuentas ya cerradas o solo abiertas?",
             esperado={"todas": ["ingreso"], "alguna": ["abierto", "factur", "estimado"]},
             fuente="docs_tableros/tablero_control_facturacion/md/inicio.md"))

    # ------------------------------------------------------------ DEMANDA INSATISFECHA (4)
    R = DEM[1]
    CAL = "CALENDARIO[Date]"
    v = "419eebff31ea51a00005"
    f, s = ctx(R, "SOLICITUD CAMAS", v, "este_ano", CAL)
    add(case("G27", DEM, "numero", "cuantos pacientes se quedaron sin la cama que pidieron este año",
             page="SOLICITUD CAMAS", visual=v, skipped=s, dax=numero("SUM('SOLICITUD DE CAMAS'[DEMANDA_INS])", f),
             tol=0.0))
    v = "61e30c3c030199001657"
    f, s = ctx(R, "TRIAGES", v, "este_ano", CAL)
    add(case("G28", DEM, "agrupado", "de la gente que se fue del triage sin ser atendida en 2026, de q eps son la mayoria",
             page="TRIAGES", visual=v, skipped=s,
             dax=agrupado("TRIAGE[TERNOMCOM]", "DISTINCTCOUNT(TRIAGE[OID])", f, top=5), tol=0.0, top_keys=3))
    v = "87e601ddc8fc43f57002"
    fs, s = ctx(R, "CONSOLIDADO", v, extra=[rango(CAL, SEP)])
    fo, _ = ctx(R, "CONSOLIDADO", v, extra=[rango(CAL, OCT)])
    add(case("G29", DEM, "comparacion", "la demanda que no pudimos cubrir subio o bajo de septiembre a octubre?",
             page="CONSOLIDADO", visual=v, skipped=s,
             dax=comparacion("[TOTAL_DEMANDA_INSATISFECHA]", {"septiembre": fs, "octubre": fo}), tol=0.01))
    add(case("G30", DEM, "definicion", "cuando una cirugia cuenta como no oportuna en demanda insatisfecha",
             esperado={"todas": ["45"], "alguna": ["dias", "días", "espera"]},
             fuente="docs_tableros/tablero_demanda_insatisfecha/md/cirugias.md"))

    # ------------------------------------------------------------ ANTIBIÓTICOS (2)
    R = ANTI[1]
    f, s = ctx(R, "ANTIBIOTICOS", None, extra=[contiene("ANTIBIOTICOS[SERVICIO]", "UCI")])
    add(case("G31", ANTI, "numero", "dosis de antibiotico aplicadas en las ucis", page="ANTIBIOTICOS", skipped=s,
             dax=numero("[TOTAL DOSIS SUMINISTRADAS]", f), tol=0.005,
             criterio="Tarjeta TOTAL DOSIS SUMINISTRADAS de ANTIBIOTICOS con SERVICIO que contiene «UCI» (lo que se ve "
                      "al elegir las UCI en el segmentador de servicio)."))
    f, s = ctx(R, "ANTIBIOTICOS", None, extra=[contiene("ANTIBIOTICOS[ANTIBIOTICO]", "MEROPENEM")])
    add(case("G32", ANTI, "numero", "ahorita cuantos pacientes estan con meropenem", page="ANTIBIOTICOS", skipped=s,
             dax=numero("[PAC_ACT]", f), tol=0.0,
             criterio="Tarjeta [PAC_ACT] con ANTIBIOTICO que contiene «MEROPENEM» (barra de MEROPENEM del gráfico "
                      "PACIENTES ACTIVOS POR TIPO DE ANTIBIÓTICO). Si hoy no hay, la verdad es «sin datos»."))

    # ------------------------------------------------------------ LAVANDERÍA (2)
    R = LAV[1]
    add(case("G33", LAV, "definicion", "en lavanderia como se sabe si un pesaje es de la mañana, tarde o noche",
             esperado={"todas": ["turno"], "alguna": ["1", "mañana", "manana"]},
             fuente="docs_tableros/tablero_lavanderia/md/_diccionario.md"))
    fj, s = ctx(R, "Página 1", None, extra=[rango("LAVANDERIA[Fecha]", JUL)])
    fa, _ = ctx(R, "Página 1", None, extra=[rango("LAVANDERIA[Fecha]", AGO)])
    add(case("G34", LAV, "comparacion", "en q mes entro mas ropa a lavanderia, julio o agosto", page="Página 1",
             skipped=s, unidad="kg", tol=0.01,
             dax=comparacion("SUM(LAVANDERIA[Peso])", {"julio": fj, "agosto": fa}),
             criterio="Suma de LAVANDERIA[Peso] por mes de LAVANDERIA[Fecha] (el PBIP local no trae visuales; "
                      "mismo criterio que LV01)." + MODELO_DOC))

    # ------------------------------------------------------------ NAOS (2)
    R = NAOS[1]
    v = "7bc30393506827ee7a49"
    f, s = ctx(R, "LISTADO", v)
    add(case("G35", NAOS, "agrupado", "los de naos en que servicio estan hospitalizados", page="LISTADO", visual=v,
             skipped=s, dax=agrupado("PACIENTES[HSUNOMBRE]", "DISTINCTCOUNT(PACIENTES[ADNINGRESO])", f), tol=0.0))
    v = "79ae233890566352860c"
    f, s = ctx(R, "LISTADO", v, extra=[contiene("PACIENTES[HSUNOMBRE]", "CUARTO PISO")])
    add(case("G36", NAOS, "numero", "cuantos naos hay en el cuarto piso", page="LISTADO", visual=v, skipped=s,
             dax=numero("DISTINCTCOUNT(PACIENTES[AINCONSEC])", f), tol=0.0,
             nota="Tarjeta PACIENTES de LISTADO con el servicio CUARTO PISO (norte y sur)."))

    # ------------------------------------------------------------ RECEPCIÓN TÉCNICA (3)
    R = RT[1]
    v = "8608de18640a4d5031b3"
    f, s = ctx(R, "CANTIDADES", v)
    add(case("G37", RT, "numero", "lo pendiente en recepcion tecnica cuanto tiempo tarda en promedio en dispensarse",
             page="CANTIDADES", visual=v, skipped=s, dax=numero("AVERAGE(PENDIENTES_RT[TIEMPO_DISPENSACION])", f),
             tol=0.03, nota="DirectQuery en vivo."))
    v = "74373c3c8375a5527a15"
    f, s = ctx(R, "INGRESOS DÍA", v)
    add(case("G38", RT, "agrupado", "lo que entro hoy a recepcion tecnica, cuanto hay en cada etapa?", page="INGRESOS DÍA",
             visual=v, skipped=s,
             dax=agrupado("TablaPedidosActuales[NomEstado]", "DISTINCTCOUNT(TablaPedidosActuales[OidRTPedido])", f),
             tol=0.0, top_keys=4))
    v = "dc615fa67119e2d1b905"
    f, s = ctx(R, "PROMEDIO GESTION MENSUAL ", v)
    add(case("G39", RT, "numero", "cantidad de registros que muestra promedio gestion mensual de recepcion tecnica",
             page="PROMEDIO GESTION MENSUAL", visual=v, skipped=s,
             dax=numero("SUM('PROMEDIO GESTION MENSUAL'[CANTIDAD_REGISTROS])", f), tol=0.0))

    # ------------------------------------------------------------ REFERENCIA (4)
    R = REF[1]
    f, s = ctx(R, "INICIO")
    add(case("G40", REF, "numero", "cuantas horas en promedio nos demoramos en contestarle a quien nos remite",
             page="INICIO", skipped=s, dax=numero("AVERAGE(REFERENCIA[TIEMPO_REMISION])", f), unidad="h", tol=0.03,
             criterio="Tarjeta TIEMPO PROMEDIO RESPUESTA de INICIO: promedio en horas de REFERENCIA[TIEMPO_REMISION], "
                      "últimos 30 días (inicio.md)." + MODELO_DOC))
    add(case("G41", REF, "agrupado", "solicitudes de referencia por rango de horas de respuesta", page="INICIO",
             skipped=s, dax=agrupado("REFERENCIA[RANGO_REMISION]", "DISTINCTCOUNT(REFERENCIA[OID])", f), tol=0.0,
             top_keys=4,
             criterio="Torta «SOLICITUDES por TIEMPO» de INICIO (RANGO_REMISION: 0-24, 24-72, 72-120, >120 h)."
                      + MODELO_DOC))
    add(case("G42", REF, "lista", "cuales son los motivos por los que no se acepta un paciente remitido",
             page="INICIO", skipped=s,
             dax="EVALUATE FILTER(VALUES(REFERENCIA[CAUSA_MAYUSC]), NOT ISBLANK(REFERENCIA[CAUSA_MAYUSC]) && "
                 "REFERENCIA[CAUSA_MAYUSC] <> \"\")", cobertura=0.6,
             criterio="Porciones de la torta «SOLICITUDES por CAUSA NO ACEPTACIÓN» de INICIO (CAUSA_MAYUSC sin la "
                      "porción en blanco), últimos 30 días." + MODELO_DOC))
    add(case("G43", REF, "numero", "q edad tienen en promedio los pacientes q nos refieren", page="INICIO", skipped=s,
             dax=numero("AVERAGE(REFERENCIA[ANOS])", f), tol=0.02,
             criterio="Tarjeta PROMEDIO DE EDAD de INICIO: promedio de REFERENCIA[ANOS], últimos 30 días."
                      + MODELO_DOC))

    # ------------------------------------------------------------ CVC (2)
    R = CVC[1]
    f, s = ctx(R, "CVC", None, "este_ano", "'calendario'[Date]")
    add(case("G44", CVC, "numero", "cuanto dinero se fue en compras que llegaron mas caras este año", page="CVC",
             skipped=s, dax=numero("SUM(COSTOS_PRODUCTOS[COMPRA_TOTAL])", f + [igual("COSTOS_PRODUCTOS[ESTADO]", "AUMENTÓ")]),
             unidad="$", tol=0.01,
             criterio="Tarjeta TOTAL COMPRAS CON AUMENTO de CVC: suma de COMPRA_TOTAL con ESTADO = AUMENTÓ (cvc.md), año "
                      "en curso por 'calendario'[Date]." + MODELO_DOC))
    f, s = ctx(R, "CVC", None, extra=[rango("'calendario'[Date]", OCT)])
    add(case("G45", CVC, "numero", "cuantos productos diferentes se compraron en octubre segun cvc", page="CVC",
             skipped=s, dax=numero("DISTINCTCOUNT(COSTOS_PRODUCTOS[OIDPRODUCTO])", f), tol=0.01,
             alternativas=[numero("COUNTROWS(COSTOS_PRODUCTOS)", f)],
             criterio="Tarjeta TOTAL PRODUCTOS de CVC en octubre de 2026. El cálculo está «por confirmar» en cvc.md: se "
                      "acepta el conteo de productos distintos o el de registros." + MODELO_DOC))

    # ------------------------------------------------------------ PERFIL DE MORBILIDAD (2)
    R = MORB[1]
    f, s = ctx(R, "PERFIL DE MORBILIDAD", None, extra=[rango("'Calendario'[Date]", A2025)])
    add(case("G46", MORB, "agrupado", "egresos del 2025 separados por hombres y mujeres", page="PERFIL DE MORBILIDAD",
             skipped=s, dax=agrupado("'MATRIZ 2024'[Sexo]", "COUNTROWS('MATRIZ 2024')", f), tol=0.01, top_keys=2,
             criterio="Tabla por sexo de PERFIL DE MORBILIDAD (ATENCIONES = filas de MATRIZ 2024), año 2025."
                      + MODELO_DOC))
    add(case("G47", MORB, "numero", "promedio de edad de los egresados en 2025 en morbilidad",
             page="PERFIL DE MORBILIDAD", skipped=s, dax=numero("AVERAGE('MATRIZ 2024'[Edad])", f), tol=0.02,
             criterio="Tarjeta PROMEDIO (EDAD) de PERFIL DE MORBILIDAD, año 2025." + MODELO_DOC))

    # ------------------------------------------------------------ FUERA DE ALCANCE (3)
    rechazo = {"rechazo": True}
    crit = "Fuera de alcance: debe rechazarse sin consultar Power BI y sin inventar cifras."
    add(case("G48", BRIEF, "fuera_alcance", "quien gano el partido de anoche?", esperado=rechazo, criterio=crit))
    add(case("G49", FACT, "fuera_alcance", "como hago un buscarv en excel para cruzar dos listas", esperado=rechazo,
             criterio=crit))
    add(case("G50", ANTI, "fuera_alcance", "cuanto acetaminofen le puedo dar a un niño de 20 kilos",
             esperado=rechazo, criterio=crit + " Es consejo clínico (dosis), no una pregunta administrativa."))
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
    from tests.real import similitud
    hits = similitud.check(BANCO)
    if hits:
        print("PREGUNTAS PARECIDAS a las de otros bancos:")
        for h in hits:
            print(f"  {h['id']} ~ {h['otro']} ({h['puntaje']}): {h['pregunta']!r} ~ {h['otra']!r}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
