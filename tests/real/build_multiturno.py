"""
Genera tests/real/banco_multiturno.json: conversaciones de 2 a 4 turnos con
los seguimientos reales de un usuario administrativo. Cada turno lleva SU
verdad DAX con el mismo criterio del banco (tests/real/RETOMAR.md): la cifra
que el usuario ve en el tablero = medida del visual + filtros de informe,
página y visual + periodo pedido.

Categorías:
  periodo      «¿y el mes anterior?», «¿y ayer?», «¿y en todo 2025?»
  agrupacion   «¿y por servicio?», «ahora sin agrupar»
  filtro       «¿y en urgencias?», «¿y para NUEVA EPS?»
  indicador    «¿y las camas ocupadas?» (otro indicador del mismo tablero)
  pronombre    «¿y de esas cuántas…?», «¿en qué servicios están?»
  correccion   «no, me refería a…»
  clic         primer turno con contrapregunta legítima: clic en la opción y seguir

Si un turno recibe una contrapregunta, run_multiturno pulsa la opción de
«elegir» (o la del modelo/página de la verdad), como run_banco.

    python -X utf8 -m tests.real.build_multiturno
    python -X utf8 -m tests.real.run_multiturno --sim
"""
import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.real import env as real_env  # noqa: E402
from tests.real.build_banco import (  # noqa: E402
    ATEN, BRIEF, CITAS, DEM, EPS, FACT, FARM, LAV, TIEMPOS, agrupado, case, ctx, find_visual, numero)
from tests.real.build_holdout import rango  # noqa: E402

HERE = Path(__file__).resolve().parent
BANCO = HERE / "banco_multiturno.json"

P = {
    "hoy": ("{HOY}", "{HOY}"),
    "ayer": ("{AYER}", "{AYER}"),
    "este_mes": ("{INI_MES}", "{HOY}"),
    "mes_pasado": ("{INI_MES_PASADO}", "{FIN_MES_PASADO}"),
    "mes_antepasado": ("{INI_MES_ANTEPASADO}", "{FIN_MES_ANTEPASADO}"),
    "semana_pasada": ("{INI_SEMANA_PASADA}", "{FIN_SEMANA_PASADA}"),
    "este_ano": ("{INI_ANO}", "{HOY}"),
    "ano_pasado": ("{INI_ANO_PASADO}", "{FIN_ANO_PASADO}"),
    "septiembre": ("DATE(2026, 9, 1)", "DATE(2026, 9, 30)"),
    "agosto": ("DATE(2026, 8, 1)", "DATE(2026, 8, 31)"),
    "octubre": ("DATE(2026, 10, 1)", "DATE(2026, 10, 31)"),
    "2025": ("DATE(2025, 1, 1)", "DATE(2025, 12, 31)"),
}
CATEGORIAS = ("periodo", "agrupacion", "filtro", "indicador", "pronombre", "correccion", "clic")


def per(col, nombre):
    return rango(col, P[nombre])


def contiene(col, texto):
    return f'KEEPFILTERS(FILTER(ALL({col}), CONTAINSSTRING({col}, "{texto}")))'


def igual(col, valor):
    return f'KEEPFILTERS(FILTER(ALL({col}), {col} = "{valor}"))'


def turno(n, entrada, board, tipo, **kw):
    item = case(f"_t{n}", board, tipo, entrada, **kw)
    item.pop("id")
    item.pop("turnos_extra", None)
    item["entrada"] = item.pop("pregunta")
    return {"n": n, **item}


def conv(cid, categoria, descripcion, turnos):
    assert categoria in CATEGORIAS, categoria
    assert 2 <= len(turnos) <= 4, cid
    return {"id": cid, "categoria": categoria, "tablero": turnos[0]["tablero"], "descripcion": descripcion,
            "turnos": turnos}


def lav(n, entrada, periodo, tipo="numero", col=None, **kw):
    """Turno de lavandería: Fecha (verdad) o FechaRegistro (alternativa), como LV01."""
    R = LAV[1]
    f, s = ctx(R, "Página 1", None, extra=[per("LAVANDERIA[Fecha]", periodo)])
    f2, _ = ctx(R, "Página 1", None, extra=[per("LAVANDERIA[FechaRegistro]", periodo)])
    if tipo == "numero":
        dax, alt = numero("SUM(LAVANDERIA[Peso])", f), numero("SUM(LAVANDERIA[Peso])", f2)
    else:
        dax, alt = agrupado(col, "SUM(LAVANDERIA[Peso])", f), agrupado(col, "SUM(LAVANDERIA[Peso])", f2)
    return turno(n, entrada, LAV, tipo, page="Página 1", skipped=s, dax=dax, alternativas=[alt], unidad="kg",
                 tol=0.01, nota="Fecha o FechaRegistro (mismo criterio que LV01).", **kw)


def build():
    real_env.setup_env()
    convs = []
    add = convs.append

    # ================================================================ PERIODO
    R, CAL = TIEMPOS[1], "Calendario[FECHA]"
    v = "3d3e950347e7ce76fbd1"  # tarjeta AVG(OPORTUNIDAD_TRIAGE[MIN]) de RESUMEN

    def triage(n, entrada, periodo, R=R, CAL=CAL, v=v):
        f, s = ctx(R, "RESUMEN", v, extra=[per(CAL, periodo)])
        return turno(n, entrada, TIEMPOS, "numero", page="RESUMEN", visual=v, skipped=s,
                     dax=numero("AVERAGE(OPORTUNIDAD_TRIAGE[MIN])", f), unidad="min")

    add(conv("MT01", "periodo", "Tiempo de triage: mes pasado → el anterior → este mes", [
        triage(1, "cuanto fue el tiempo promedio de triage en urgencias el mes pasado", "mes_pasado"),
        triage(2, "¿y el mes anterior a ese?", "mes_antepasado"),
        triage(3, "¿y en lo que va de este mes?", "este_mes")]))

    add(conv("MT02", "periodo", "Kilos de ropa: ayer → hoy → semana pasada", [
        lav(1, "cuantos kilos de ropa se lavaron ayer", "ayer"),
        lav(2, "¿y hoy?", "hoy"),
        lav(3, "¿y en toda la semana pasada?", "semana_pasada")]))

    R, CAL = ATEN[1], "'Calendario'[Date]"

    def egresos(n, entrada, periodo, R=R, CAL=CAL, **kw):
        f, s = ctx(R, "INDICADORES", None, extra=[per(CAL, periodo)])
        return turno(n, entrada, ATEN, "numero", page="INDICADORES", skipped=s, dax=numero("[Total Egresos]", f),
                     tol=0.01, elegir="Total Egresos", **kw)

    add(conv("MT03", "periodo", "Egresos de Atenciones: septiembre → agosto → 2025", [
        egresos(1, "cuantos egresos hubo en septiembre", "septiembre"),
        egresos(2, "¿y en agosto?", "agosto"),
        egresos(3, "¿y en todo el 2025?", "2025")]))

    R, CAL = DEM[1], "CALENDARIO[Date]"
    v_tri = find_visual(R, "TRIAGES", "TRIAGE.OID", "card")

    def triages_no(n, entrada, periodo, R=R, CAL=CAL):
        f, s = ctx(R, "TRIAGES", v_tri, extra=[per(CAL, periodo)])
        return turno(n, entrada, DEM, "numero", page="TRIAGES", visual=v_tri, skipped=s,
                     dax=numero("DISTINCTCOUNT(TRIAGE[OID])", f), tol=0.0)

    add(conv("MT04", "periodo", "Triages no atendidos (Demanda): mes pasado → el anterior → año", [
        triages_no(1, "cuantos triages quedaron sin atender el mes pasado", "mes_pasado"),
        triages_no(2, "¿y el mes anterior?", "mes_antepasado"),
        triages_no(3, "¿y en lo que va del año?", "este_ano")]))

    # ================================================================ AGRUPACIÓN
    R = BRIEF[1]
    ic = "DISTINCTCOUNT(INTERCONSULTAS[OID_SOLICITUD])"
    f1, s = ctx(R, "INTERCONSULTAS", "582d978a007e443658b1")
    f2, _ = ctx(R, "INTERCONSULTAS", "5a2062cbc4d90c72d0c8")
    f3, _ = ctx(R, "INTERCONSULTAS", "38374005eae24ba064e3")
    add(conv("MT05", "agrupacion", "Interconsultas pendientes: total → por servicio → por especialidad", [
        turno(1, "cuantas interconsultas estan pendientes de respuesta", BRIEF, "numero", page="INTERCONSULTAS",
              visual="582d978a007e443658b1", skipped=s, dax=numero(ic, f1), tol=0.0),
        turno(2, "¿y por servicio?", BRIEF, "agrupado", page="INTERCONSULTAS", visual="5a2062cbc4d90c72d0c8",
              skipped=s, dax=agrupado("INTERCONSULTAS[HSUNOMBRE]", ic, f2), tol=0.0),
        turno(3, "¿y por especialidad?", BRIEF, "agrupado", page="INTERCONSULTAS", visual="38374005eae24ba064e3",
              skipped=s, dax=agrupado("INTERCONSULTAS[GEEDESCRI]", ic, f3), tol=0.0)]))

    add(conv("MT06", "agrupacion", "Ropa lavada este mes: total → por turno → sin agrupar", [
        lav(1, "cuanta ropa se ha lavado este mes", "este_mes"),
        lav(2, "¿por turno?", "este_mes", tipo="agrupado", col="LAVANDERIA[TURNO_OK]", top_keys=3),
        lav(3, "ahora sin agrupar, solo el total", "este_mes")]))

    R, CAL = ATEN[1], "'Calendario'[Date]"
    f, s = ctx(R, "INDICADORES", None, extra=[per(CAL, "mes_pasado")])
    add(conv("MT07", "agrupacion", "Egresos del mes pasado: total → por servicio → el mayor", [
        egresos(1, "cuantos egresos tuvimos el mes pasado", "mes_pasado"),
        turno(2, "¿y por servicio?", ATEN, "agrupado", page="INDICADORES", skipped=s,
              dax=agrupado("DIM_SERVICIO[SERVICIO_HOMOLOGADO]", "[Total Egresos]", f), tol=0.01,
              elegir="Total Egresos"),
        turno(3, "¿cuál servicio tuvo más?", ATEN, "agrupado", page="INDICADORES", skipped=s,
              dax=agrupado("DIM_SERVICIO[SERVICIO_HOMOLOGADO]", "[Total Egresos]", f, top=3), tol=0.01, top_keys=1,
              elegir="Total Egresos")]))

    R = CITAS[1]
    v_esp = find_visual(R, "INICIO", "EN_ESPERA.OID_CITA", "card",
                        extra=lambda x: x["filters"] and x["filters"][0].endswith("IN {0}))"))
    f1, s = ctx(R, "INICIO", v_esp)
    f2, _ = ctx(R, "EN ESPERA X ESPECIALIDAD", "c920868794ad0a9c5f6e")
    f3, _ = ctx(R, "EN ESPERA X ESPECIALIDAD", "1552eb3df989fe3f0cb2")
    add(conv("MT08", "agrupacion", "Citas en espera: total → por especialidad → por aseguradora", [
        turno(1, "cuantas citas estan en espera", CITAS, "numero", page="INICIO", visual=v_esp, skipped=s,
              dax=numero("DISTINCTCOUNT(EN_ESPERA[OID_CITA])", f1), tol=0.0),
        turno(2, "¿cómo se reparten por especialidad?", CITAS, "agrupado", page="EN ESPERA X ESPECIALIDAD",
              visual="c920868794ad0a9c5f6e", skipped=s,
              dax=agrupado("EN_ESPERA[GEEDESCRI]", "DISTINCTCOUNT(EN_ESPERA[OID_CITA])", f2), tol=0.0),
        turno(3, "¿y por aseguradora?", CITAS, "agrupado", page="EN ESPERA X ESPECIALIDAD",
              visual="1552eb3df989fe3f0cb2", skipped=s,
              dax=agrupado("ASEGURADORA[ASEGURADORA_HM]", "COUNT(EN_ESPERA[OID_CITA])", f3, top=5), tol=0.0)]))

    # ================================================================ FILTRO
    R = BRIEF[1]
    v_pac = find_visual(R, "INICIO", "PACIENTES X ASEGURADORA.ADNINGRESO", "card")
    pac = "DISTINCTCOUNT('PACIENTES X ASEGURADORA'[ADNINGRESO])"
    f, s = ctx(R, "INICIO", v_pac)
    ase = "'PACIENTES X ASEGURADORA'[TERNOMCOM]"
    add(conv("MT09", "filtro", "Pacientes hospitalizados: total → NUEVA EPS → SURA", [
        turno(1, "cuantos pacientes hay hospitalizados ahora", BRIEF, "numero", page="INICIO", visual=v_pac,
              skipped=s, dax=numero(pac, f), tol=0.0),
        turno(2, "¿y de esos cuántos son de NUEVA EPS?", BRIEF, "numero", page="INICIO", visual=v_pac, skipped=s,
              dax=numero(pac, f + [contiene(ase, "NUEVA EMPRESA PROMOTORA")]), tol=0.0,
              criterio="Tarjeta TOTAL PACIENTES de INICIO con la aseguradora NUEVA EPS. En TERNOMCOM se llama «NUEVA "
                       "EMPRESA PROMOTORA DE SALUD EPS S.A.» (auditoría multiturno: «NUEVA EPS» no existe como texto)."),
        turno(3, "¿y de SURA?", BRIEF, "numero", page="INICIO", visual=v_pac, skipped=s,
              dax=numero(pac, f + [contiene(ase, "SURA")]), tol=0.0)]))

    R = FACT[1]
    v = "c159d258360e91566173"
    f, s = ctx(R, "INICIO", v)
    fac = "SUM(ULT_GESTION[FACTURADO])"
    # Auditoría multiturno: TERNOMCOM trae el nombre legal («NUEVA EMPRESA PROMOTORA DE SALUD EPS S.A.»), no
    # «NUEVA EPS» (la verdad daba vacío). Por confirmar con tests/real/consultas_auditoria.json.
    eps = contiene("ULT_GESTION[TERNOMCOM]", "NUEVA EMPRESA PROMOTORA")
    add(conv("MT10", "filtro", "Valor estimado: total → NUEVA EPS → de eso, hospitalario", [
        turno(1, "cual es el valor estimado pendiente de facturar", FACT, "numero", page="INICIO", visual=v,
              skipped=s, dax=numero(fac, f), unidad="$", tol=0.01),
        turno(2, "¿y para NUEVA EPS?", FACT, "numero", page="INICIO", visual=v, skipped=s,
              dax=numero(fac, f + [eps]), unidad="$", tol=0.01),
        turno(3, "¿y de eso cuánto es hospitalario?", FACT, "numero", page="INICIO", visual=v, skipped=s,
              dax=numero(fac, f + [eps, contiene("ULT_GESTION[TIPO_INGRESO]", "HOSPITAL")]), unidad="$", tol=0.01,
              criterio="Tarjeta de valor estimado de INICIO con NUEVA EPS (turno anterior) y TIPO_INGRESO "
                       "hospitalario: «de eso» acumula el filtro.")]))

    R = BRIEF[1]
    tri = "DISTINCTCOUNT(TRIAGES[OID_TRIAGE])"
    f1, s = ctx(R, "URGENCIAS", "e45fda46778f618639fd")
    f2, _ = ctx(R, "URGENCIAS", "2ed97a310c3ae03ccb64")
    add(conv("MT11", "filtro", "Triages del Briefing: generales → obstétricos", [
        turno(1, "cuantos triages lleva hoy urgencias segun el briefing", BRIEF, "numero", page="URGENCIAS",
              visual="e45fda46778f618639fd", skipped=s, dax=numero(tri, f1), tol=0.0),
        turno(2, "¿y los obstétricos?", BRIEF, "numero", page="URGENCIAS", visual="2ed97a310c3ae03ccb64", skipped=s,
              dax=numero(tri, f2), tol=0.0)]))

    R = CITAS[1]
    f, s = ctx(R, "INICIO", v_esp)
    esp = "EN_ESPERA[GEEDESCRI]"

    def espera(n, entrada, texto, exacto=None, f=f, s=s):
        # Auditoría multiturno (MT12.2): elegir la especialidad exacta en el segmentador («CARDIOLOGIA», 659) es
        # tan válido como la familia por CONTAINSSTRING («CARDIOLOG», 881): se acepta como alternativa.
        alts = [numero("DISTINCTCOUNT(EN_ESPERA[OID_CITA])", f + [igual(esp, exacto)])] if exacto else None
        return turno(n, entrada, CITAS, "numero", page="INICIO", visual=v_esp, skipped=s,
                     dax=numero("DISTINCTCOUNT(EN_ESPERA[OID_CITA])", f + [contiene(esp, texto)]), tol=0.0,
                     alternativas=alts,
                     criterio="Tarjeta de citas en espera de INICIO con la especialidad pedida (CONTAINSSTRING sobre "
                              "EN_ESPERA[GEEDESCRI]: lo que se ve al elegirla en el segmentador).")

    add(conv("MT12", "filtro", "Citas en espera por especialidad: ortopedia → cardiología → pediatría", [
        espera(1, "cuantas citas hay en espera para ortopedia", "ORTOPED"),
        espera(2, "¿y para cardiología?", "CARDIOLOG", exacto="CARDIOLOGIA"),
        espera(3, "¿y para pediatría?", "PEDIATR")]))

    # ================================================================ INDICADOR
    R = BRIEF[1]
    camas = "DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO])"

    def cama(n, entrada, vid, R=R):
        f, s = ctx(R, "GESTIÓN CAMAS", vid)
        return turno(n, entrada, BRIEF, "numero", page="GESTIÓN CAMAS", visual=vid, skipped=s, dax=numero(camas, f),
                     tol=0.0)

    f, s = ctx(R, "GESTIÓN CAMAS", "06f2271d25d40aa1e082")
    ocupacion = turno(3, "¿y el porcentaje de ocupación?", BRIEF, "numero", page="GESTIÓN CAMAS",
                      visual="06f2271d25d40aa1e082", skipped=s, dax=numero("[%OCUPACION]", f), unidad="%",
                      porcentaje=True, elegir="BRIEFING", contrapregunta_ok=True)
    add(conv("MT13", "indicador", "Camas: disponibles → ocupadas → % ocupación", [
        cama(1, "cuantas camas disponibles hay ahorita", "04c3f320b40299303088"),
        cama(2, "¿y las ocupadas?", "e8da3d43077a771d4c89"),
        ocupacion]))

    R, CAL = TIEMPOS[1], "Calendario[FECHA]"

    def resumen(n, entrada, vid, expr, R=R, CAL=CAL):
        f, s = ctx(R, "RESUMEN", vid, extra=[per(CAL, "este_mes")])
        return turno(n, entrada, TIEMPOS, "numero", page="RESUMEN", visual=vid, skipped=s, dax=numero(expr, f),
                     unidad="min")

    add(conv("MT14", "indicador", "Tiempos de urgencias este mes: admisión → consulta → triage", [
        resumen(1, "tiempo promedio de admision en urgencias este mes", "9a6006e9bf111f860603",
                "AVERAGE(CONSULTA_URGENCIAS[MINUTOS_ADMISION])"),
        resumen(2, "¿y el de consulta?", "7909eb29acca72dcb3c5", "AVERAGE(CONSULTA_URGENCIAS[MINUTOS_CONSULTA])"),
        resumen(3, "¿y el de triage?", "3d3e950347e7ce76fbd1", "AVERAGE(OPORTUNIDAD_TRIAGE[MIN])")]))

    R = FARM[1]

    def farm(n, entrada, page, vid, expr, R=R):
        f, s = ctx(R, page, vid)
        return turno(n, entrada, FARM, "numero", page=page, visual=vid, skipped=s, dax=numero(expr, f), tol=0.0)

    add(conv("MT15", "indicador", "Farmacia: suministros pendientes → bajo mínimo → vencen en 30 días", [
        farm(1, "cuantos suministros pendientes tiene farmacia", "INICIO", "a7cca487d35dc5fbfac5",
             "DISTINCTCOUNT(PENDIENTES_FARMACIA[HCNFOLIO])"),
        farm(2, "¿y cuántos productos están por debajo del mínimo?", "INICIO", "7f327b479dc6334ae2e8",
             "DISTINCTCOUNT(CANTIDAD_MINIMA[CODIGO])"),
        farm(3, "¿y cuántos se vencen en los próximos 30 días?", "MEDICAMENTOS VENCIDOS", "76fe7ef9727ff90aad41",
             "DISTINCTCOUNT(VENCIMIENTO_PRODUCTOS[IPRCODIGO])")]))

    R = EPS[1]
    v_ep2 = find_visual(R, "TRIAGES ATENDIDOS", "OPORTUNIDAD_TRIAGE.OID_TRIAGE", "card",
                        extra=lambda x: "NOT (" in (x["filters"] or [""])[0] and "MUERTO" in x["filters"][0])
    f1, s = ctx(R, "TRIAGES ATENDIDOS", v_ep2)
    f2, _ = ctx(R, "TRIAGES ATENDIDOS", "b272611ab547ea5020c0")
    f3, _ = ctx(R, "TRIAGES ATENDIDOS", "4d40a4f67ba188041e3a")
    add(conv("MT16", "indicador", "Tablero EPS: triages atendidos → prioritarias confirmadas → ocupación", [
        turno(1, "cuantos triages atendidos registra el tablero eps", EPS, "numero", page="TRIAGES ATENDIDOS",
              visual=v_ep2, skipped=s, dax=numero("COUNT(OPORTUNIDAD_TRIAGE[OID_TRIAGE])", f1), tol=0.0),
        turno(2, "¿y las consultas prioritarias confirmadas?", EPS, "numero", page="TRIAGES ATENDIDOS",
              visual="b272611ab547ea5020c0", skipped=s, dax=numero("COUNT(CONSULTAS_PRIORITARIAS[PACNUMDOC])", f2),
              tol=0.0, elegir="EPS", contrapregunta_ok=True),
        turno(3, "¿y la ocupación de urgencias?", EPS, "numero", page="TRIAGES ATENDIDOS",
              visual="4d40a4f67ba188041e3a", skipped=s, dax=numero("[%OCUPACIONALC]", f3), unidad="%",
              porcentaje=True, elegir="EPS", contrapregunta_ok=True,
              criterio="Tarjeta %OCUPACIONALC del TABLERO EPS: el turno anterior fija el tablero; contrapregunta "
                       "legítima igual que EP01.")]))

    # ================================================================ PRONOMBRES Y ELIPSIS
    R = BRIEF[1]
    f1, s = ctx(R, "EGRESOS PROBABLES", "76f79896573d21108d56")
    f2, _ = ctx(R, "EGRESOS PROBABLES", "6b0bd9028ac5f7feb43f")
    f3, _ = ctx(R, "EGRESOS PROBABLES", "5e7d29a53e4547905c70")
    ep = "DISTINCTCOUNT('EGRESOS PROBABLES'[AINCONSEC])"
    add(conv("MT17", "pronombre", "Egresos probables: total → «de esos» efectivos → «en qué servicios están»", [
        turno(1, "cuantos egresos probables hay para hoy", BRIEF, "numero", page="EGRESOS PROBABLES",
              visual="76f79896573d21108d56", skipped=s, dax=numero(ep, f1), tol=0.0),
        turno(2, "¿y de esos cuántos ya salieron?", BRIEF, "numero", page="EGRESOS PROBABLES",
              visual="6b0bd9028ac5f7feb43f", skipped=s,
              dax=numero("SUM('EGRESOS PROBABLES'[EGRESO_EFECTIVO_HOY])", f2), tol=0.0),
        turno(3, "¿en qué servicios están?", BRIEF, "agrupado", page="EGRESOS PROBABLES",
              visual="5e7d29a53e4547905c70", skipped=s, dax=agrupado("'EGRESOS PROBABLES'[HSUNOMBRE]", ep, f3),
              tol=0.0, criterio="«están» = los egresos probables del turno 1: dona por servicio de EGRESOS PROBABLES.")]))

    R, CAL = DEM[1], "CALENDARIO[Date]"
    cit = "DISTINCTCOUNT('CITAS MEDICAS'[OID])"
    f1, s = ctx(R, "CITAS", "66e6dd12d613a960264f", extra=[per(CAL, "este_ano")])
    f2, _ = ctx(R, "CITAS", "b18910ca086d0609e975", extra=[per(CAL, "este_ano")])
    f3, _ = ctx(R, "CITAS", "66e6dd12d613a960264f", extra=[per(CAL, "octubre")])
    add(conv("MT18", "pronombre", "Citas canceladas por la institución: año → motivos → «de esas» en octubre", [
        turno(1, "cuantas citas cancelo la institucion este año", DEM, "numero", page="CITAS",
              visual="66e6dd12d613a960264f", skipped=s, dax=numero(cit, f1), tol=0.0, elegir="conteo de OID",
              contrapregunta_ok=True),
        turno(2, "¿y por qué motivos fueron?", DEM, "agrupado", page="CITAS", visual="b18910ca086d0609e975",
              skipped=s, dax=agrupado("'CITAS MEDICAS'[CCCDESCRI]", cit, f2), tol=0.0, top_keys=3),
        turno(3, "¿cuántas de esas fueron en octubre?", DEM, "numero", page="CITAS", visual="66e6dd12d613a960264f",
              skipped=s, dax=numero(cit, f3), tol=0.0)]))

    R = BRIEF[1]
    sol = "DISTINCTCOUNT('SOLICITUD CAMAS'[oid])"

    def solicitud(n, entrada, vid, R=R):
        f, s = ctx(R, "SOLICITUD CAMAS", vid)
        return turno(n, entrada, BRIEF, "numero", page="SOLICITUD CAMAS", visual=vid, skipped=s, dax=numero(sol, f),
                     tol=0.0)

    add(conv("MT19", "pronombre", "Solicitudes de cama: pendientes → «de esas» hombres → mujeres", [
        solicitud(1, "cuantas solicitudes de cama hay pendientes", "6245fa3c1d7e780c00c5"),
        solicitud(2, "¿cuántas de esas son de hombres?", "1849cfb80d5da806c989"),
        solicitud(3, "¿y de mujeres?", "3ad290d796500a0b7b9c")]))

    # ================================================================ CORRECCIÓN
    add(conv("MT20", "correccion", "Camas disponibles → «no, me refería a las en transición»", [
        cama(1, "cuantas camas disponibles hay", "04c3f320b40299303088"),
        cama(2, "no, me refería a las que están en transición", "d76b7140e006cec53960")]))

    R, CAL = TIEMPOS[1], "Calendario[FECHA]"
    f, s = ctx(R, "RESUMEN", "47fa83a530a50be09558", extra=[per(CAL, "mes_pasado")])
    add(conv("MT21", "correccion", "Triage del mes pasado → «no, me refería a la estancia en urgencias»", [
        triage(1, "tiempo promedio de triage del mes pasado", "mes_pasado"),
        turno(2, "no, me refería al tiempo que pasan los pacientes en urgencias", TIEMPOS, "numero", page="RESUMEN",
              visual="47fa83a530a50be09558", skipped=s,
              dax=numero("AVERAGE(TIEMPO_URGENCIAS[TiempoMinutosSalidaUrgencias])", f), unidad="min",
              criterio="Corrección del indicador conservando el periodo (mes pasado): tarjeta de estancia en "
                       "urgencias de RESUMEN.")]))

    add(conv("MT22", "correccion", "Ropa de este año → «perdón, quise decir el año pasado»", [
        lav(1, "kilos de ropa lavada este año", "este_ano"),
        lav(2, "perdón, quise decir el año pasado", "ano_pasado")]))

    # ================================================================ CLIC EN LA CONTRAPREGUNTA Y SEGUIR
    R = BRIEF[1]
    v_eg = find_visual(R, "INGRESOS Y EGRESOS", "EGRESOS.INGRESO", "card")
    f1, s = ctx(R, "INGRESOS Y EGRESOS", v_eg)
    f2, _ = ctx(R, "INGRESOS Y EGRESOS", "9644aae01364bc463224")
    add(conv("MT23", "clic", "Egresos de ayer (clic BRIEFING) → por aseguradora", [
        turno(1, "cuantos egresos hubo ayer", BRIEF, "numero", page="INGRESOS Y EGRESOS", visual=v_eg, skipped=s,
              dax=numero("DISTINCTCOUNT(EGRESOS[INGRESO])", f1), tol=0.0, elegir="BRIEFING", contrapregunta_ok=True),
        turno(2, "¿y por aseguradora?", BRIEF, "agrupado", page="INGRESOS Y EGRESOS", visual="9644aae01364bc463224",
              skipped=s, dax=agrupado("TercerosRelacionados[nombre_tercero]", "COUNT(EGRESOS[INGRESO])", f2),
              alternativas=[agrupado("TercerosRelacionados[nombre_tercero]", "DISTINCTCOUNT(EGRESOS[INGRESO])", f2)],
              tol=0.0, elegir="BRIEFING",
              criterio="Barras de egresos por tercero de INGRESOS Y EGRESOS (día anterior, filtro de página sin "
                       "HOSPITALIZACION PARCIAL); se acepta conteo o conteo distinto de INGRESO.")]))

    f1, s = ctx(R, "GESTIÓN CAMAS", "06f2271d25d40aa1e082")
    f2, _ = ctx(R, "INICIO", "79c772ea0d5c89268706")
    occ = dict(unidad="%", porcentaje=True, tol=0.01, elegir="BRIEFING")
    add(conv("MT24", "clic", "Nivel de ocupación (clic BRIEFING) → por servicio → el más lleno", [
        turno(1, "cual es el nivel de ocupacion?", BRIEF, "numero", page="GESTIÓN CAMAS",
              visual="06f2271d25d40aa1e082", skipped=s, dax=numero("[%OCUPACION]", f1), contrapregunta_ok=True, **occ),
        turno(2, "¿y por servicio?", BRIEF, "agrupado", page="INICIO", visual="79c772ea0d5c89268706", skipped=s,
              dax=agrupado("SERVICIOS[HSUNOMBRE]", "[%OCUPACION]", f2), **occ),
        turno(3, "¿cuál está más lleno?", BRIEF, "agrupado", page="INICIO", visual="79c772ea0d5c89268706", skipped=s,
              dax=agrupado("SERVICIOS[HSUNOMBRE]", "[%OCUPACION]", f2, top=3), top_keys=1, **occ)]))

    R, CAL = ATEN[1], "'Calendario'[Date]"

    def cirugias(n, entrada, periodo, R=R, CAL=CAL, **kw):
        f, s = ctx(R, "CIRUGIAS", None, extra=[per(CAL, periodo)])
        return turno(n, entrada, ATEN, "numero", page="CIRUGIAS", skipped=s, dax=numero("[TOTAL_CIRUGIAS]", f),
                     tol=0.01, elegir="TABLERO DE ATENCIONES", **kw)

    add(conv("MT25", "clic", "Cirugías del año (clic ATENCIONES) → el año pasado", [
        cirugias(1, "cuantas cirugias se han hecho en lo que va del año", "este_ano", contrapregunta_ok=True),
        cirugias(2, "¿y el año pasado?", "ano_pasado")]))

    def triages_ai(n, entrada, periodo, R=R, CAL=CAL, **kw):
        f, s = ctx(R, "TRIAGE", None, extra=[per(CAL, periodo)])
        return turno(n, entrada, ATEN, "numero", page="TRIAGE", skipped=s, dax=numero("[TOTAL_TRIAGES]", f),
                     tol=0.005, elegir="ATENCIONES", **kw)

    add(conv("MT26", "clic", "Triages de 2025 (clic ATENCIONES) → este año", [
        triages_ai(1, "cuantos triages hubo en 2025", "2025", contrapregunta_ok=True),
        triages_ai(2, "¿y en lo que va de este año?", "este_ano")]))
    return convs


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.parse_args(argv)
    convs = build()
    ids = [c["id"] for c in convs]
    assert len(ids) == len(set(ids)), "ids repetidos"
    BANCO.write_text(json.dumps({"version": 1, "multiturno": True, "conversaciones": convs}, ensure_ascii=False,
                                indent=1, default=str), encoding="utf-8")
    turnos = sum(len(c["turnos"]) for c in convs)
    print(f"{len(convs)} conversaciones, {turnos} turnos -> {BANCO}")


if __name__ == "__main__":
    main()
