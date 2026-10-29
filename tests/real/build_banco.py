"""
Genera tests/real/banco_real.json: preguntas administrativas realistas con su
DAX de VERDAD (medida del visual + filtros de informe, página y visual leídos
del PBIR de tableros/, y el periodo pedido).

    python -X utf8 -m tests.real.build_banco            # solo arma el JSON
    python -X utf8 -m tests.real.build_banco --valores  # además ejecuta cada DAX de verdad
                                                        # (solo agregados) y guarda el valor de referencia

Los periodos se escriben con marcadores que run_banco.py reemplaza el día de
la corrida: {HOY} {AYER} {INI_MES} {INI_MES_PASADO} {FIN_MES_PASADO}
{INI_ANO} {INI_AGO} {FIN_AGO} {INI_ANO_PASADO} {FIN_ANO_PASADO}.
"""
import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.real import env as real_env  # noqa: E402

HERE = Path(__file__).resolve().parent
BANCO = HERE / "banco_real.json"

BRIEF = ("BRIEFING HOSPITALARIO", "BRIEFING HOSPITALARIO")
TIEMPOS = ("TABLERO TIEMPOS URGENCIAS", "TABLERO TIEMPOS URGENCIAS")
ATEN = ("TABLERO DE ATENCIONES INSTITUCIONALES", "TABLERO DE ATENCIONES INSTITUCIONALES")
CITAS = ("ASIGNACION DE CITAS", "ASIGNACION DE CITAS")
EPS = ("TABLERO EPS", "TABLERO EPS")
FARM = ("TABLERO_FARMACIA", "TABLERO_FARMACIA")
FACT = ("Tablero Control Facturacion", "Tablero Control de Facturacion")
DEM = ("Demanda Insatisfecha", "Demanda Insatisfecha")
ANTI = ("TABLERO_ANTIBIOTICOS", "TABLERO_ANTIBIOTICOS")
LAV = ("Tablero_lavanderia", "Tablero_lavanderia")

PERIODOS = {
    "mes_pasado": ("{INI_MES_PASADO}", "{FIN_MES_PASADO}"),
    "este_mes": ("{INI_MES}", "{HOY}"),
    "este_ano": ("{INI_ANO}", "{HOY}"),
    "ayer": ("{AYER}", "{AYER}"),
    "hoy": ("{HOY}", "{HOY}"),
    "agosto": ("{INI_AGO}", "{FIN_AGO}"),
    "ano_pasado": ("{INI_ANO_PASADO}", "{FIN_ANO_PASADO}"),
}


def find_visual(report, page, field, vtype=None, nth=0, extra=None):
    from tests.real import pbir

    hits = [v for v in pbir.visuals(report, page)
            if any(field.casefold() in f.casefold() for f in v["fields"])
            and (vtype is None or v["type"] == vtype)
            and (extra is None or extra(v))]
    if len(hits) <= nth:
        raise LookupError(f"{report}/{page}: no hay visual con {field} ({vtype})")
    return hits[nth]["id"]


def period_filter(col, periodo):
    ini, fin = PERIODOS[periodo]
    return f"KEEPFILTERS(FILTER(ALL({col}), {col} >= {ini} && {col} <= {fin}))"


def ctx(report, page, visual=None, periodo=None, fecha=None, extra=()):
    """Filtros (lista DAX) del visual + periodo."""
    from tests.real import pbir

    filters, skipped = pbir.filters_dax(report, page, visual)
    if periodo:
        filters.append(period_filter(fecha, periodo))
    filters += list(extra)
    return filters, skipped


def calc(expr, filters):
    if not filters:
        return expr
    return "CALCULATE(" + expr + ",\n    " + ",\n    ".join(filters) + ")"


def numero(expr, filters):
    return 'EVALUATE ROW("v", ' + calc(expr, filters) + ")"


def agrupado(col, expr, filters, top=None):
    inner = f'SUMMARIZECOLUMNS({col}, ' + ", ".join(filters + [f'"v", {expr}']) + ")"
    if top:
        inner = f"TOPN({top}, {inner}, [v], DESC)"
    return "EVALUATE " + inner


def lista(col, filters):
    inner = f"CALCULATETABLE(VALUES({col}), " + ", ".join(filters) + ")" if filters else f"VALUES({col})"
    return "EVALUATE " + inner


def case(cid, board, tipo, pregunta, *, dax=None, page=None, visual=None, skipped=(), unidad="", tol=0.02,
         elegir=None, contrapregunta_ok=False, turnos=None, esperado=None, fuente=None, nota=None,
         alternativas=None, top_keys=5, porcentaje=False, cobertura=0.6):
    model, report = board
    item = {
        "id": cid, "tablero": model, "tipo": tipo, "pregunta": pregunta,
        "turnos_extra": turnos or [], "elegir": elegir, "contrapregunta_aceptable": contrapregunta_ok,
    }
    if dax:
        item["verdad"] = {
            "modelo": model, "informe": report, "pagina": page, "visual": visual, "dax": dax,
            "unidad": unidad, "tolerancia": tol, "porcentaje": porcentaje,
            "filtros_no_traducidos": list(skipped),
        }
        if tipo == "agrupado":
            item["verdad"]["top_keys"] = top_keys
        if tipo == "lista":
            item["verdad"]["cobertura_minima"] = cobertura
        if alternativas:
            item["verdad"]["alternativas"] = alternativas
    if esperado:
        item["esperado"] = esperado
    if fuente:
        item["fuente"] = fuente
    if nota:
        item["nota"] = nota
    return item


def build():
    real_env.setup_env()
    cases = []
    add = cases.append

    # ------------------------------------------------------------ BRIEFING
    R = BRIEF[1]
    v = "06f2271d25d40aa1e082"
    f, s = ctx(R, "GESTIÓN CAMAS", v)
    add(case("BH01", BRIEF, "numero", "cual es el nivel de ocupacion?", page="GESTIÓN CAMAS", visual=v, skipped=s,
             dax=numero("[%OCUPACION]", f), unidad="%", porcentaje=True, elegir="BRIEFING", contrapregunta_ok=True,
             nota="Tarjeta %OCUPACION de GESTIÓN CAMAS. Conversación real del usuario."))
    for cid, vid, q in (("BH02", "04c3f320b40299303088", "cuantas camas disponibles hay ahorita"),
                        ("BH03", "e8da3d43077a771d4c89", "cuántas camas ocupadas tenemos?"),
                        ("BH04", "3a9714665e097d231a23", "cuantas camas tiene el hospital en total")):
        f, s = ctx(R, "GESTIÓN CAMAS", vid)
        add(case(cid, BRIEF, "numero", q, page="GESTIÓN CAMAS", visual=vid, skipped=s,
                 dax=numero("DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO])", f), tol=0.0))
    v = "d7cc5ae83dea62107544"
    f, s = ctx(R, "GESTIÓN CAMAS", v)
    add(case("BH05", BRIEF, "lista", "dame una lista de las areas que tiene el hospital", page="GESTIÓN CAMAS",
             visual=v, skipped=s, dax=lista("SERVICIOS[NOM_SERV]", f), cobertura=0.5,
             nota="Conversación real. Verdad: servicios del segmentador SERVICIO de GESTIÓN CAMAS."))
    v = find_visual(R, "INTERCONSULTAS", "OID_SOLICITUD", "card")
    f, s = ctx(R, "INTERCONSULTAS", v)
    add(case("BH06", BRIEF, "numero", "cuantas interconsultas hay sin responder?", page="INTERCONSULTAS", visual=v,
             skipped=s, dax=numero("DISTINCTCOUNT(INTERCONSULTAS[OID_SOLICITUD])", f), tol=0.0))
    v = find_visual(R, "INTERCONSULTAS", "GEEDESCRI", "clusteredBarChart")
    f, s = ctx(R, "INTERCONSULTAS", v)
    add(case("BH07", BRIEF, "agrupado", "interconsultas pendientes por especialidad", page="INTERCONSULTAS",
             visual=v, skipped=s, dax=agrupado("INTERCONSULTAS[GEEDESCRI]", "DISTINCTCOUNT(INTERCONSULTAS[OID_SOLICITUD])", f),
             tol=0.0))
    v = find_visual(R, "EGRESOS PROBABLES", "AINCONSEC", "card")
    f, s = ctx(R, "EGRESOS PROBABLES", v)
    add(case("BH08", BRIEF, "numero", "cuantos egresos probables hay para hoy", page="EGRESOS PROBABLES", visual=v,
             skipped=s, dax=numero("DISTINCTCOUNT('EGRESOS PROBABLES'[AINCONSEC])", f), tol=0.0))
    v = find_visual(R, "INICIO", "PACIENTES X ASEGURADORA.ADNINGRESO", "card")
    f, s = ctx(R, "INICIO", v)
    add(case("BH09", BRIEF, "numero", "cuantos pacientes hay hospitalizados en este momento", page="INICIO",
             visual=v, skipped=s, dax=numero("DISTINCTCOUNT('PACIENTES X ASEGURADORA'[ADNINGRESO])", f), tol=0.0))
    v = find_visual(R, "INICIO", "TERNOMCOM", "clusteredBarChart")
    f, s = ctx(R, "INICIO", v)
    add(case("BH10", BRIEF, "agrupado", "cantidad de pacientes por aseguradora", page="INICIO", visual=v,
             skipped=s, dax=agrupado("'PACIENTES X ASEGURADORA'[TERNOMCOM]",
                                     "DISTINCTCOUNT('PACIENTES X ASEGURADORA'[ADNINGRESO])", f), tol=0.0))
    v = find_visual(R, "SOLICITUD CAMAS", "oid", "card", extra=lambda x: len(x["filters"]) == 3)
    f, s = ctx(R, "SOLICITUD CAMAS", v)
    add(case("BH11", BRIEF, "numero", "cuantas solicitudes de cama estan pendientes?", page="SOLICITUD CAMAS",
             visual=v, skipped=s, dax=numero("DISTINCTCOUNT('SOLICITUD CAMAS'[oid])", f), tol=0.0))
    f, s = ctx(R, "INICIO")
    add(case("BH12", BRIEF, "numero", "como esta el nedocs hoy?", page="INICIO", skipped=s,
             dax=numero("[TotalN]", f), tol=0.01))
    add(case("BH13", BRIEF, "definicion", "que significa el NEDOCS y como se calcula?",
             esperado={"todas": ["nedocs"], "alguna": ["85.8", "85,8", "600", "13.4", "13,4", "5.64", "5,64", "sobreocupación", "saturación"]},
             fuente="docs_tableros/tablero_briefing_hospitalario/md/detalle_nedocs.md"))
    v = find_visual(R, "INGRESOS Y EGRESOS", "EGRESOS.INGRESO", "card")
    f, s = ctx(R, "INGRESOS Y EGRESOS", v)
    add(case("BH14", BRIEF, "numero", "cuantos egresos hubo ayer", page="INGRESOS Y EGRESOS", visual=v, skipped=s,
             dax=numero("DISTINCTCOUNT(EGRESOS[INGRESO])", f), tol=0.0,
             nota="La tabla EGRESOS del briefing trae solo el día anterior (verificado: MIN = MAX = ayer)."))
    v = find_visual(R, "URGENCIAS", "OID_TRIAGE", "card",
                    extra=lambda x: any("MUERTO" in t for t in x["filters"]))
    f, s = ctx(R, "URGENCIAS", v)
    add(case("BH15", BRIEF, "numero", "cuantos triages van en urgencias segun el briefing", page="URGENCIAS",
             visual=v, skipped=s, dax=numero("DISTINCTCOUNT(TRIAGES[OID_TRIAGE])", f), tol=0.0))
    v = find_visual(R, "ATENCIONES POR ASEGURADOR", "ATENCIONES_SERVICIO.SERVICIO", "clusteredBarChart")
    f, s = ctx(R, "ATENCIONES POR ASEGURADOR", v, "este_ano", "ATENCIONES_SERVICIO[FECHA]")
    add(case("BH16", BRIEF, "agrupado", "atenciones por servicio de este año en el briefing",
             page="ATENCIONES POR ASEGURADOR", visual=v, skipped=s,
             dax=agrupado("ATENCIONES_SERVICIO[SERVICIO]", "SUM(ATENCIONES_SERVICIO[TOTAL_ATENCIONES])", f), tol=0.005))
    v = find_visual(R, "ATENCIONES POR ASEGURADOR", "TOTAL_ATENCIONES", "card")
    f, s = ctx(R, "ATENCIONES POR ASEGURADOR", v, "mes_pasado", "ATENCIONES_SERVICIO[FECHA]")
    add(case("BH17", BRIEF, "numero", "cuantas atenciones hubo el mes pasado por asegurador en total?",
             page="ATENCIONES POR ASEGURADOR", visual=v, skipped=s,
             dax=numero("SUM(ATENCIONES_SERVICIO[TOTAL_ATENCIONES])", f), tol=0.005, contrapregunta_ok=True,
             elegir="BRIEFING"))
    add(case("BH18", BRIEF, "comportamiento",
             "necsito saber que tantas especialidades se estan manejando en el area e urgencias y a cantidad de paciente que tiene cada una",
             esperado={"no_inventar": True,
                       "aceptable": "Tabla de especialidades con pacientes en urgencias desde una fuente real (p. ej. PACIENTES X ASEGURADORA[ESPECIALIDAD] con HSUNOMBRE URGENCIAS, casi siempre en blanco) o una contrapregunta útil; nunca cifras sin fuente."},
             nota="Conversación real del usuario. No hay un visual que responda exactamente; se evalúa que no invente."))

    # ------------------------------------------------------------ TIEMPOS URGENCIAS
    R = TIEMPOS[1]
    CAL = "Calendario[FECHA]"
    v = find_visual(R, "RESUMEN_D", "TIEMPO_PARA_TRIAGE_DIA", "card")
    f, s = ctx(R, "RESUMEN_D", v)
    add(case("TU01", TIEMPOS, "numero", "cual es el tiempo promedio para triage hoy?", page="RESUMEN_D", visual=v,
             skipped=s, dax=numero("AVERAGE(TRIAGES_DIA[TIEMPO_PARA_TRIAGE_DIA])", f), unidad="min", tol=0.02))
    v = find_visual(R, "RESUMEN", "MINUTOS_CONSULTA", "card")
    f, s = ctx(R, "RESUMEN", v, "mes_pasado", CAL)
    add(case("TU02", TIEMPOS, "numero", "tiempo promedio de atencion en consulta de urgencias el mes pasado",
             page="RESUMEN", visual=v, skipped=s, dax=numero("AVERAGE(CONSULTA_URGENCIAS[MINUTOS_CONSULTA])", f),
             unidad="min"))
    v = find_visual(R, "RESUMEN", "OPORTUNIDAD_TRIAGE.MIN", "card")
    f, s = ctx(R, "RESUMEN", v, "mes_pasado", CAL)
    add(case("TU03", TIEMPOS, "numero", "cuanto se demoran en hacer el triage en promedio el mes pasado",
             page="RESUMEN", visual=v, skipped=s, dax=numero("AVERAGE(OPORTUNIDAD_TRIAGE[MIN])", f), unidad="min"))
    f2, _ = ctx(R, "RESUMEN", v, "agosto", CAL)
    add(case("TU03b", TIEMPOS, "numero", "cuanto se demoran en hacer el triage en promedio el mes pasado",
             turnos=["texto: y en agosto?"], page="RESUMEN", visual=v, skipped=s,
             dax=numero("AVERAGE(OPORTUNIDAD_TRIAGE[MIN])", f2), unidad="min",
             nota="Seguimiento: la verdad es la del último turno (agosto)."))
    v = find_visual(R, "TIEMPO TRIAGE", "OID_TRIAGE", "lineClusteredColumnComboChart")
    f, s = ctx(R, "TIEMPO TRIAGE", v, "este_mes", CAL)
    add(case("TU04", TIEMPOS, "numero", "cuantos triages se han hecho este mes en urgencias", page="TIEMPO TRIAGE",
             visual=v, skipped=s, dax=numero("DISTINCTCOUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE])", f), tol=0.005))
    v = find_visual(R, "INTERCONSULTAS", "%ATENDIDO", "card")
    f, s = ctx(R, "INTERCONSULTAS", v, "este_mes", CAL)
    add(case("TU05", TIEMPOS, "numero", "porcentaje de interconsultas atendidas este mes", page="INTERCONSULTAS",
             visual=v, skipped=s, dax=numero("[%ATENDIDO]", f), unidad="%", porcentaje=True))
    v = find_visual(R, "INTERCONSULTAS", "TIEMPO_RESPUESTA_INTERCONSULTA", "lineClusteredColumnComboChart")
    f, s = ctx(R, "INTERCONSULTAS", v, "mes_pasado", CAL)
    add(case("TU06", TIEMPOS, "agrupado", "tiempo promedio de respuesta de interconsultas por especialidad el mes pasado",
             page="INTERCONSULTAS", visual=v, skipped=s,
             dax=agrupado("INTERCONSULTA[GEEDESCRI]", "AVERAGE(INTERCONSULTA[TIEMPO_RESPUESTA_INTERCONSULTA])", f, top=15),
             unidad="h", tol=0.03))
    v = find_visual(R, "TIEMPO EGRESO", "TIEMPO_EGRESO_OK", "card")
    f, s = ctx(R, "TIEMPO EGRESO", v, "este_ano", CAL)
    add(case("TU07", TIEMPOS, "numero", "tiempo promedio para el egreso en urgencias este año", page="TIEMPO EGRESO",
             visual=v, skipped=s, dax=numero("AVERAGE(TIEMPO_PARA_EGRESO[TIEMPO_EGRESO_OK])", f), unidad="min"))
    v = find_visual(R, "IMAGENES", "SOLICITUDES_CANT", "card")
    f, s = ctx(R, "IMAGENES", v, "mes_pasado", CAL)
    add(case("TU08", TIEMPOS, "numero", "cuantas imagenes se tomaron en urgencias el mes pasado", page="IMAGENES",
             visual=v, skipped=s, dax=numero("SUM(IMAGENES[SOLICITUDES_CANT])", f), tol=0.005))
    v = find_visual(R, "EXAMENES", "TIEMPO_RESPUESTA", "card")
    f, s = ctx(R, "EXAMENES", v, "este_mes", CAL)
    add(case("TU09", TIEMPOS, "numero", "cual es el tiempo de respuesta de los examenes este mes", page="EXAMENES",
             visual=v, skipped=s, dax=numero("AVERAGE(EXAMENES[TIEMPO_RESPUESTA])", f)))
    v = find_visual(R, "RESUMEN", "OPORTUNIDAD_TRIAGE.MIN", "card")
    fa, s = ctx(R, "RESUMEN", v, "agosto", CAL)
    fs, _ = ctx(R, "RESUMEN", v, "mes_pasado", CAL)
    add(case("TU10", TIEMPOS, "comparacion", "compara el tiempo promedio de triage de agosto contra el del mes pasado",
             page="RESUMEN", visual=v, skipped=s, unidad="min",
             dax='EVALUATE ROW("agosto", ' + calc("AVERAGE(OPORTUNIDAD_TRIAGE[MIN])", fa) + ', "mes_pasado", '
                 + calc("AVERAGE(OPORTUNIDAD_TRIAGE[MIN])", fs) + ")"))
    add(case("TU11", TIEMPOS, "definicion", "como se calcula el tiempo para triage?",
             esperado={"todas": ["triage"], "alguna": ["digiturno", "turno", "minutos"]},
             fuente="docs_tableros/tablero_tiempos_urgencias/md/resumen_d.md"))
    v = find_visual(R, "INTERCONSULTAS", "SOLICITUDES", "card")
    f, s = ctx(R, "INTERCONSULTAS", v, "ayer", CAL)
    add(case("TU12", TIEMPOS, "agrupado", "identifica la cantidad de interconsultas del día de ayer y su respectiva especialidad",
             page="INTERCONSULTAS", visual=v, skipped=s,
             dax=agrupado("INTERCONSULTA[GEEDESCRI]", "SUM(INTERCONSULTA[SOLICITUDES])", f), tol=0.0,
             nota="Conversación real del usuario. Verdad: tarjeta INTERCONSULTAS SOLICITADAS por especialidad, día de ayer."))
    v = find_visual(R, "TIEMPO ESTANCIA", "TiempoMinutosSalidaUrgencias", "card")
    f, s = ctx(R, "TIEMPO ESTANCIA", v, "mes_pasado", CAL)
    add(case("TU13", TIEMPOS, "numero", "cuanto tiempo duran los pacientes en urgencias en promedio el mes pasado",
             page="TIEMPO ESTANCIA", visual=v, skipped=s,
             dax=numero("AVERAGE(TIEMPO_URGENCIAS[TiempoMinutosSalidaUrgencias])", f), unidad="min"))

    # ------------------------------------------------------------ ATENCIONES INSTITUCIONALES
    R = ATEN[1]
    CAL = "'Calendario'[Date]"
    f, s = ctx(R, "INDICADORES", None, "mes_pasado", CAL)
    add(case("AI01", ATEN, "numero", "cuantos egresos hubo el mes pasado", page="INDICADORES", skipped=s,
             dax=numero("[Total Egresos]", f), tol=0.01, contrapregunta_ok=True, elegir="ATENCIONES"))
    f, s = ctx(R, "CIRUGIAS", None, "este_ano", CAL)
    add(case("AI02", ATEN, "numero", "cuantas cirugias se han hecho en lo que va del año", page="CIRUGIAS",
             skipped=s, dax=numero("[TOTAL_CIRUGIAS]", f), tol=0.01))
    v = find_visual(R, "INDICADORES", "GIRO_CAMA1", "lineChart")
    f, s = ctx(R, "INDICADORES", v, "mes_pasado", CAL)
    add(case("AI03", ATEN, "numero", "cual fue el giro cama del mes pasado", page="INDICADORES", visual=v,
             skipped=s, dax=numero("[GIRO_CAMA1]", f), tol=0.03))
    f, s = ctx(R, "TRIAGE", None, "ano_pasado", CAL)
    add(case("AI04", ATEN, "numero", "cuantos triages hubo en 2025", page="TRIAGE", skipped=s,
             dax=numero("[TOTAL_TRIAGES]", f), tol=0.005, contrapregunta_ok=True, elegir="ATENCIONES"))
    f, s = ctx(R, "URGENCIAS", None, "mes_pasado", CAL)
    add(case("AI05", ATEN, "numero", "cuantas consultas de urgencias se hicieron el mes pasado", page="URGENCIAS",
             skipped=s, dax=numero("[Total_consultas_urgencias]", f), tol=0.01, contrapregunta_ok=True,
             elegir="ATENCIONES"))
    f, s = ctx(R, "PARTOS", None, "este_ano", CAL)
    add(case("AI06", ATEN, "numero", "cuantos partos van este año", page="PARTOS", skipped=s,
             dax=numero("COUNTROWS(PARTOS_DRIVE)", f), tol=0.01))
    v = find_visual(R, " LABORATORIO PATOLOGICO", "Consecutivo", "card")
    f, s = ctx(R, " LABORATORIO PATOLOGICO", v)
    add(case("AI07", ATEN, "numero", "cuantos reportes de patologia van este año", page="LABORATORIO PATOLOGICO",
             visual=v, skipped=s, dax=numero("COUNT(LABORATORIOS_PATOLOGICOS[Consecutivo])",
                                            f + ["KEEPFILTERS(FILTER(ALL(LABORATORIOS_PATOLOGICOS[FechaSolicitud]), YEAR(LABORATORIOS_PATOLOGICOS[FechaSolicitud]) = YEAR({HOY})))"]),
             tol=0.0))
    f, s = ctx(R, "INDICADORES", None, "mes_pasado", CAL)
    add(case("AI08", ATEN, "agrupado", "egresos por servicio del mes pasado", page="INDICADORES", skipped=s,
             dax=agrupado("DIM_SERVICIO[SERVICIO_HOMOLOGADO]", "[Total Egresos]", f), tol=0.01,
             contrapregunta_ok=True, elegir="ATENCIONES"))
    add(case("AI09", ATEN, "definicion", "que es el giro cama?",
             esperado={"todas": ["cama"], "alguna": ["egresos", "egreso"]},
             fuente="docs_tableros/tablero_de_atenciones_institucionales/md/indicadores.md"))

    # ------------------------------------------------------------ ASIGNACION DE CITAS
    R = CITAS[1]
    v = find_visual(R, "INICIO", "EN_ESPERA.OID_CITA", "card",
                    extra=lambda x: x["filters"] and x["filters"][0].endswith("IN {0}))"))
    f, s = ctx(R, "INICIO", v)
    add(case("AC01", CITAS, "numero", "cuantas citas hay en espera?", page="INICIO", visual=v, skipped=s,
             dax=numero("DISTINCTCOUNT(EN_ESPERA[OID_CITA])", f), tol=0.0))
    v = find_visual(R, "INICIO", "CITAS_ASIGNADAS.OID_CITA", "card")
    f, s = ctx(R, "INICIO", v)
    add(case("AC02", CITAS, "numero", "cuantas consultas asignadas hay", page="INICIO", visual=v, skipped=s,
             dax=numero("DISTINCTCOUNT(CITAS_ASIGNADAS[OID_CITA])", f), tol=0.0))
    v = find_visual(R, "OFERTA ESPECIALIDADES", "%INASISTENCIA", "card")
    f, s = ctx(R, "OFERTA ESPECIALIDADES", v)
    add(case("AC03", CITAS, "numero", "cual es el porcentaje de inasistencia de las citas", page="OFERTA ESPECIALIDADES",
             visual=v, skipped=s, dax=numero("[%INASISTENCIA]", f), unidad="%", porcentaje=True))
    v = find_visual(R, "EN ESPERA X ESPECIALIDAD", "GEEDESCRI", "clusteredBarChart")
    f, s = ctx(R, "EN ESPERA X ESPECIALIDAD", v)
    add(case("AC04", CITAS, "agrupado", "citas en espera por especialidad", page="EN ESPERA X ESPECIALIDAD",
             visual=v, skipped=s, dax=agrupado("EN_ESPERA[GEEDESCRI]", "DISTINCTCOUNT(EN_ESPERA[OID_CITA])", f), tol=0.0))
    v = find_visual(R, "INICIO", "Tiempo_Asignacion", "card")
    f, s = ctx(R, "INICIO", v)
    add(case("AC05", CITAS, "numero", "cuantos dias se demora en promedio la asignacion de una cita", page="INICIO",
             visual=v, skipped=s, dax=numero("AVERAGE(EN_ESPERA[Tiempo_Asignacion])", f), unidad="días"))

    # ------------------------------------------------------------ EPS
    R = EPS[1]
    v = find_visual(R, "TRIAGES ATENDIDOS", "%OCUPACIONALC", "card")
    f, s = ctx(R, "TRIAGES ATENDIDOS", v)
    add(case("EP01", EPS, "numero", "cual es la ocupacion de urgencias", page="TRIAGES ATENDIDOS", visual=v,
             skipped=s, dax=numero("[%OCUPACIONALC]", f), unidad="%", porcentaje=True, contrapregunta_ok=True,
             elegir="EPS"))
    v = find_visual(R, "TRIAGES ATENDIDOS", "OPORTUNIDAD_TRIAGE.OID_TRIAGE", "card",
                    extra=lambda x: "NOT (" in (x["filters"] or [""])[0] and "MUERTO" in x["filters"][0])
    f, s = ctx(R, "TRIAGES ATENDIDOS", v)
    add(case("EP02", EPS, "numero", "cuantos triages atendidos hay en el tablero eps", page="TRIAGES ATENDIDOS",
             visual=v, skipped=s, dax=numero("COUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE])", f), tol=0.0))
    v = find_visual(R, "TRIAGES ATENDIDOS", "HCENTRIAGE", "card")
    f, s = ctx(R, "TRIAGES ATENDIDOS", v)
    add(case("EP03", EPS, "numero", "cuantos pacientes observados hay en urgencias", page="TRIAGES ATENDIDOS",
             visual=v, skipped=s, dax=numero("COUNT(PACIENTES_OBSERVADOS[HCENTRIAGE])", f), tol=0.0,
             contrapregunta_ok=True))
    v = find_visual(R, "TRIAGES ATENDIDOS", "CONSULTAS_PRIORITARIAS", "card")
    f, s = ctx(R, "TRIAGES ATENDIDOS", v)
    add(case("EP04", EPS, "numero", "cuantas consultas prioritarias confirmadas hay", page="TRIAGES ATENDIDOS",
             visual=v, skipped=s, dax=numero("COUNT(CONSULTAS_PRIORITARIAS[PACNUMDOC])", f), tol=0.0,
             contrapregunta_ok=True))

    # ------------------------------------------------------------ FARMACIA
    R = FARM[1]
    v = find_visual(R, "INICIO", "HCNFOLIO", "card")
    f, s = ctx(R, "INICIO", v)
    add(case("FM01", FARM, "numero", "cuantos suministros pendientes hay en farmacia", page="INICIO", visual=v,
             skipped=s, dax=numero("DISTINCTCOUNT(PENDIENTES_FARMACIA[HCNFOLIO])", f), tol=0.0))
    v = find_visual(R, "INICIO", "CANTIDAD_MINIMA.CODIGO", "card")
    f, s = ctx(R, "INICIO", v)
    add(case("FM02", FARM, "numero", "cuantos productos estan por debajo del inventario minimo", page="INICIO",
             visual=v, skipped=s, dax=numero("DISTINCTCOUNT(CANTIDAD_MINIMA[CODIGO])", f), tol=0.0))
    v = find_visual(R, "MEDICAMENTOS VENCIDOS", "IPRCODIGO", "card", extra=lambda x: "<= 1" in " ".join(x["filters"]))
    f, s = ctx(R, "MEDICAMENTOS VENCIDOS", v)
    add(case("FM03", FARM, "numero", "medicamentos que se vencen en los proximos 30 dias", page="MEDICAMENTOS VENCIDOS",
             visual=v, skipped=s, dax=numero("DISTINCTCOUNT(VENCIMIENTO_PRODUCTOS[IPRCODIGO])", f), tol=0.0))
    f, s = ctx(R, "OPORTUNIDAD DISPENSACIÓN", None, "mes_pasado", "'TIEMPOS_DISPENSACIÓN'[hcfecfol]")
    add(case("FM04", FARM, "numero", "cual fue la oportunidad de dispensacion del mes pasado",
             page="OPORTUNIDAD DISPENSACIÓN", skipped=s,
             dax=numero("AVERAGE('TIEMPOS_DISPENSACIÓN'[OportunidadHor])", f), unidad="h", tol=0.03))

    # ------------------------------------------------------------ FACTURACIÓN
    R = FACT[1]
    v = find_visual(R, "INICIO", "FACTURADO", "card")
    f, s = ctx(R, "INICIO", v)
    add(case("FC01", FACT, "numero", "cual es el valor estimado de facturacion", page="INICIO", visual=v, skipped=s,
             dax=numero("SUM(ULT_GESTION[FACTURADO])", f), unidad="$", tol=0.01))
    v = find_visual(R, "INICIO", "TERNOMCOM", "treemap")
    f, s = ctx(R, "INICIO", v)
    add(case("FC02", FACT, "agrupado", "valor estimado por aseguradora, las 5 mas altas", page="INICIO", visual=v,
             skipped=s, dax=agrupado("ULT_GESTION[TERNOMCOM]", "SUM(ULT_GESTION[FACTURADO])", f, top=5),
             unidad="$", tol=0.01))
    v = find_visual(R, "RESUMEN FACTURACION", "TIEMPO", "card")
    f, s = ctx(R, "RESUMEN FACTURACION", v)
    add(case("FC03", FACT, "numero", "cual es el tiempo promedio de gestion de una factura", page="RESUMEN FACTURACION",
             visual=v, skipped=s, dax=numero("AVERAGE('FACTURACION PERFILES'[TIEMPO])", f), tol=0.02))
    v = find_visual(R, "EN PROCESO FACTURACION", "PROCESO_FACTURACION", "card")
    f, s = ctx(R, "EN PROCESO FACTURACION", v)
    add(case("FC04", FACT, "numero", "cuantas cuentas hay en proceso de facturacion", page="EN PROCESO FACTURACION",
             visual=v, skipped=s, dax=numero("[PROCESO_FACTURACION]", f), tol=0.0))
    v = find_visual(R, "INICIO", "FACTURADO", "card")
    f, s = ctx(R, "INICIO", v, "mes_pasado", "CALENDARIO[Date]")
    add(case("FC05", FACT, "numero", "cuanto se facturo el mes pasado", page="INICIO", visual=v, skipped=s,
             dax=numero("SUM(ULT_GESTION[FACTURADO])", f), unidad="$", tol=0.01, contrapregunta_ok=True))
    add(case("FC06", FACT, "definicion", "que mide el tiempo promedio de gestion de factura?",
             esperado={"todas": ["factura"], "alguna": ["tiempo", "días", "dias", "horas"]},
             fuente="docs_tableros/tablero_control_facturacion/md/resumen_facturacion.md"))

    # ------------------------------------------------------------ DEMANDA INSATISFECHA
    R = DEM[1]
    v = find_visual(R, "CONSOLIDADO", "TOTAL_DEMANDA_INSATISFECHA", "card")
    f, s = ctx(R, "CONSOLIDADO", v, "este_ano", "CALENDARIO[Date]")
    add(case("DI01", DEM, "numero", "cual es la demanda insatisfecha total de este año", page="CONSOLIDADO",
             visual=v, skipped=s, dax=numero("[TOTAL_DEMANDA_INSATISFECHA]", f), tol=0.01))
    v = find_visual(R, "CITAS", "OID", "card")
    f, s = ctx(R, "CITAS", v, "mes_pasado", "CALENDARIO[Date]")
    add(case("DI02", DEM, "numero", "cuantas citas cancelo la institucion el mes pasado", page="CITAS", visual=v,
             skipped=s, dax=numero("DISTINCTCOUNT('CITAS MEDICAS'[OID])", f), tol=0.0))
    v = find_visual(R, "TRIAGES", "TRIAGE.OID", "card")
    f, s = ctx(R, "TRIAGES", v, "este_ano", "CALENDARIO[Date]")
    add(case("DI03", DEM, "numero", "triages no atendidos este año", page="TRIAGES", visual=v, skipped=s,
             dax=numero("DISTINCTCOUNT(TRIAGE[OID])", f), tol=0.0))
    add(case("DI04", DEM, "definicion", "que significa demanda insatisfecha?",
             esperado={"todas": ["demanda insatisfecha"], "alguna": ["triage", "referencia", "cirug", "citas", "camas"]},
             fuente="docs_tableros/tablero_demanda_insatisfecha/md/_general.md"))

    # ------------------------------------------------------------ ANTIBIÓTICOS
    R = ANTI[1]
    f, s = ctx(R, "ANTIBIOTICOS")
    add(case("AB01", ANTI, "numero", "cuantos pacientes activos con antibiotico hay", page="ANTIBIOTICOS",
             skipped=s, dax=numero("[PAC_ACT]", f), tol=0.0))
    # El PBIR local de MONITOREO_ANTIBIOTICO usa una tabla ANTIBIOTICOSN que el
    # modelo PUBLICADO no tiene (solo ANTIBIOTICOS): la verdad usa el modelo real.
    nota_atb = "PBIR local más nuevo que el modelo publicado (ANTIBIOTICOSN no existe): verdad con ANTIBIOTICOS[PAC_ACT]."
    add(case("AB02", ANTI, "agrupado", "pacientes con antibiotico por servicio", page="MONITOREO_ANTIBIOTICO",
             dax=agrupado("ANTIBIOTICOS[SERVICIO]", "[PAC_ACT]", []), tol=0.0, nota=nota_atb))
    f, s = ctx(R, "ANTIBIOTICOS")
    add(case("AB03", ANTI, "numero", "total de dosis de antibioticos suministradas", page="ANTIBIOTICOS",
             skipped=s, dax=numero("[TOTAL DOSIS SUMINISTRADAS]", f), tol=0.005))
    add(case("AB04", ANTI, "agrupado", "cual es el antibiotico que mas se esta usando?", page="MONITOREO_ANTIBIOTICO",
             dax=agrupado("ANTIBIOTICOS[ANTIBIOTICO]", "[PAC_ACT]", [], top=3), tol=0.0, top_keys=1, nota=nota_atb))

    # ------------------------------------------------------------ LAVANDERÍA
    R = LAV[1]
    f, s = ctx(R, "Página 1", None, "mes_pasado", "LAVANDERIA[Fecha]")
    f2, _ = ctx(R, "Página 1", None, "mes_pasado", "LAVANDERIA[FechaRegistro]")
    add(case("LV01", LAV, "numero", "cuantos kilos de ropa se lavaron el mes pasado", page="Página 1", skipped=s,
             dax=numero("SUM(LAVANDERIA[Peso])", f), unidad="kg", tol=0.01,
             alternativas=[numero("SUM(LAVANDERIA[Peso])", f2)],
             nota="No está documentado si el filtro usa Fecha o FechaRegistro: se acepta cualquiera."))
    f, s = ctx(R, "Página 1", None, "este_ano", "LAVANDERIA[Fecha]")
    add(case("LV02", LAV, "agrupado", "peso de ropa por servicio en lo que va del año", page="Página 1", skipped=s,
             dax=agrupado("LAVANDERIA[SERVICIO]", "SUM(LAVANDERIA[Peso])", f, top=10), unidad="kg", tol=0.01))
    f, s = ctx(R, "Página 1")
    add(case("LV03", LAV, "agrupado", "en que turno se lava mas ropa?", page="Página 1", skipped=s,
             dax=agrupado("LAVANDERIA[TURNO_OK]", "SUM(LAVANDERIA[Peso])", f, top=4), unidad="kg", tol=0.01,
             top_keys=1))
    return cases


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--valores", action="store_true", help="ejecuta cada DAX de verdad y guarda el valor")
    args = parser.parse_args(argv)
    cases = build()
    if args.valores:
        from tests.real.run_banco import compute_truth
        for c in cases:
            if c.get("verdad"):
                c["verdad"]["referencia"] = compute_truth(c["verdad"])
                print(c["id"], json.dumps(c["verdad"]["referencia"], ensure_ascii=False, default=str)[:300], flush=True)
    BANCO.write_text(json.dumps({"version": 1, "casos": cases}, ensure_ascii=False, indent=1, default=str),
                     encoding="utf-8")
    print(f"{len(cases)} casos -> {BANCO}")


if __name__ == "__main__":
    main()
