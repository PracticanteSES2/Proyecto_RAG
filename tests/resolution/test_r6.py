"""
Ronda r6 (banco de desarrollo 94 %, holdout 67 %): reglas GENERALES, cada una
validada con preguntas NUEVAS (no del holdout ni del banco de desarrollo) sobre
el catálogo mínimo offline de r5 («Tablero Gestion» y «Tablero Ropa»).

  1. Cobertura del periodo (TU04): la holgura de un día solo vale para
     periodos de uno o dos días; «este mes» el día 3 no lo trae la tabla
     «del día anterior». Una página nombrada («página de urgencias») no
     arrastra a indicadores cuya tabla no trae el periodo.
  2. «Sin datos» explicado: qué indicador, qué periodo y hasta qué fecha trae
     datos la fuente; la tabla agrupada vacía también es «sin datos» (nunca
     «la consulta no devolvió filas»). El comparador está en
     tests/real/test_comparador.py (clase VerdadVacia).
  3. Filtro de inclusión de un visual (H20): lo común a los valores de una
     lista «en» nombra a su indicador («Triages Gineco» filtrada por los
     valores OBSTETRICA = «triages obstétricos»).
  4. Familia de valores con la página como contexto (H05): una palabra que es
     la página del indicador («urgencias» para TRIAGES) no elige un solo valor
     de la familia («obstétricos»).

Ejecutar:  python -m tests.resolution.test_r6
"""
import sys
import traceback
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.response_formatter import (  # noqa: E402
    EMPTY_RESULT_MESSAGE, empty_result_sentence, format_empty_result, format_query_plan_answer,
)
from src.dax.query_plan_dax_generator import QueryPlanDAXGenerator  # noqa: E402
from src.semantic.table_coverage import coverage_window, covers  # noqa: E402
from tests.resolution.test_r5 import GES, METRICS, builder  # noqa: E402

NOV3 = date(2026, 11, 3)


# ------------------------------------------------------------ 1. cobertura
def test_long_period_needs_the_window_start():
    yesterday = coverage_window("Visitas del día anterior con clase y fecha.", NOV3)
    assert yesterday == (date(2026, 11, 2), None), yesterday
    # Nuevas: «este mes» el 3 de noviembre, «esta semana» un jueves, «en lo que va del año».
    assert not covers(yesterday, date(2026, 11, 1), date(2026, 11, 4), NOV3)
    thursday = date(2026, 11, 5)
    assert not covers(coverage_window("Pedidos del día anterior.", thursday),
                      date(2026, 11, 2), date(2026, 11, 6), thursday)
    assert not covers(yesterday, date(2026, 1, 1), date(2026, 11, 4), NOV3)


def test_short_periods_keep_the_slack():
    yesterday = coverage_window("Visitas del día anterior.", NOV3)
    assert covers(yesterday, date(2026, 11, 2), date(2026, 11, 3), NOV3)       # ayer
    assert covers(yesterday, NOV3, date(2026, 11, 4), NOV3)                    # hoy (el corte)
    # «este mes» el día 2: la ventana empieza el 1, trae todo el periodo.
    nov2 = date(2026, 11, 2)
    assert covers(coverage_window("Visitas del día anterior.", nov2), date(2026, 11, 1), date(2026, 11, 3), nov2)
    # «ayer» sobre la tabla «de hoy» (cargada de madrugada): holgura de un día.
    assert covers(coverage_window("Ingresos de hoy.", NOV3), date(2026, 11, 2), NOV3, NOV3)


def _page_refinement_fixture(qpb, items_by_page, misses):
    """Parchea el builder para probar la regla de página nombrada sin router."""
    saved = {name: qpb.__dict__.get(name) for name in (
        "_named_pages", "_page_choices", "_metric_misses_period", "_requested_period_bounds", "_forced_plan",
        "_page_members", "_option_words", "_option_coverage", "_narrow_page_options")}
    pages = [{"page": page, "semantic_model": GES} for page in items_by_page]
    qpb._named_pages = lambda source_context: pages
    qpb._page_members = lambda page: [{"metric": m} for m in items_by_page[page["page"]]]
    qpb._page_choices = lambda question, source_context, page, offered, topic=False: {
        "items": [{"metric": m} for m in items_by_page[page["page"]]], "principal": None, "direct": True}
    qpb._metric_misses_period = lambda metric, start, end, pages=False: misses.get(metric["metric_id"])
    qpb._requested_period_bounds = lambda question: (
        ({"label": "noviembre 2026 hasta hoy"}, date(2026, 11, 1), date(2026, 11, 4))
        if "mes" in question or "año" in question else (None, None, None))
    qpb._forced_plan = lambda question, intent, item, why, consumed_tokens=None: {
        "status": "ready", "metric": item["metric"], "why": why}
    qpb._option_words = lambda question, source_context: [w for w in question.split() if len(w) > 3]
    qpb._option_coverage = lambda metric, words: [w for w in words if w.rstrip("s") in metric["label"].lower()]
    qpb._narrow_page_options = lambda question, items: items
    return saved


def _restore(qpb, saved):
    for name, value in saved.items():
        if value is None:
            qpb.__dict__.pop(name, None)
        else:
            qpb.__dict__[name] = value


def _m(metric_id, label, table):
    return {"metric_id": metric_id, "label": label, "semantic_model": GES, "table": table,
            "dax_expression": f"COUNT('{table}'[{metric_id}])"}


def test_named_page_does_not_drag_to_a_table_without_the_period():
    qpb = builder()
    visitas = _m("v", "VISITAS", "VISITAS")
    otras = _m("o", "OCUPACION", "CAMAS")
    plan = {"status": "ready", "metric": _m("h", "VISITAS HISTORICO", "VISITAS_H"),
            "source_context": {}, "metric_resolution": {"candidates": []}}
    saved = _page_refinement_fixture(qpb, {"URGENCIAS": [visitas, otras]}, {"v": "VISITAS"})
    try:
        # Nueva: «cuántas visitas van este mes en la página de urgencias»: la de la
        # página es del día anterior y lo que queda no son visitas -> la página no decide.
        out = qpb._named_page_refinement("cuantas visitas van este mes en la pagina de urgencias", {}, plan)
        assert out is None, out
        # Nueva: sin periodo, la página sí decide (no cambia la regla de r3).
        out = qpb._named_page_refinement("cuantas visitas hay en la pagina de urgencias", {}, dict(plan))
        assert out is not None and out.get("status") in ("ready", "ambiguous"), out
    finally:
        _restore(qpb, saved)


def test_named_page_keeps_options_that_cover_the_period():
    qpb = builder()
    visitas = _m("v", "VISITAS", "VISITAS")
    visitas_mes = _m("vm", "VISITAS DEL MES", "VISITAS_MES")
    plan = {"status": "ready", "metric": _m("h", "VISITAS HISTORICO", "VISITAS_H"),
            "source_context": {}, "metric_resolution": {"candidates": []}}
    saved = _page_refinement_fixture(qpb, {"URGENCIAS": [visitas, visitas_mes]}, {"v": "VISITAS"})
    try:
        # Nueva: queda la de la página que sí trae el mes -> se usa esa.
        out = qpb._named_page_refinement("visitas de este mes en la pagina de urgencias", {}, plan)
        assert out is not None and out["metric"]["metric_id"] == "vm", out
    finally:
        _restore(qpb, saved)


# ------------------------------------------------------------ 2. «sin datos»
def _plan(label="Total Visitas", period=True, filters=()):
    items = list(filters)
    if period:
        items.append({"type": "date_range", "table": "Calendario", "column": "Date", "label": "octubre 2026 (mes pasado)",
                      "start": "2026-10-01", "end": "2026-11-01"})
    return {"status": "ready", "metric": {"label": label, "dax_expression": "[Total Visitas]",
                                          "validation_status": "approved"},
            "filters": items, "semantic_model": GES, "mode": "scalar",
            "period": {"label": "octubre 2026 (mes pasado)", "start": "2026-10-01", "end": "2026-11-01"}}


def test_empty_result_names_metric_period_and_last_date():
    plan = _plan()
    result = {"status": "empty_result", "metric": "Total Visitas", "query_plan": plan, "filters": plan["filters"],
              "data_until": "2026-09-30"}
    text = format_empty_result(result)
    assert text.startswith("No hay datos de **Total Visitas**"), text
    assert "octubre" in text and "30/09/2026" in text, text
    assert "no devolvió filas" not in text
    # Sin fecha conocida: la frase sin la fecha; sin indicador ni periodo: el genérico.
    assert "hasta el" not in empty_result_sentence({**result, "data_until": None})
    assert empty_result_sentence({}) == EMPTY_RESULT_MESSAGE
    # Escalar vacío con periodo dentro de una respuesta de éxito.
    scalar = format_query_plan_answer({"value": None, "metric": "Total Visitas", "query_plan": plan,
                                       "filters": plan["filters"]})
    assert scalar.startswith("No hay datos de **Total Visitas**"), scalar
    # Sin periodo se conserva el mensaje de siempre.
    assert format_query_plan_answer({"value": None, "metric": "X"}) == EMPTY_RESULT_MESSAGE


def test_data_until_query_keeps_other_filters_and_drops_the_period():
    plan = _plan(filters=[{"type": "categorical", "table": "VISITAS", "column": "SERVICIO", "operator": "=",
                           "value": "URGENCIAS"}])
    out = QueryPlanDAXGenerator().generate_data_until(plan)
    assert out["status"] == "generated", out
    dax = out["dax"]
    assert "MAXX(FILTER(ALL('Calendario'[Date]), NOT ISBLANK(CALCULATE([Total Visitas])))" in dax, dax
    assert "URGENCIAS" in dax and "DATE(2026, 10, 1)" not in dax, dax
    assert QueryPlanDAXGenerator().generate_data_until(_plan(period=False))["status"] == "rejected"


class _Provider:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []


def _engine_with(rows_by_kind):
    from src.chatbot.query_engine import QueryEngine

    engine = QueryEngine.__new__(QueryEngine)
    engine._trace = None
    engine.query_plan_dax_generator = QueryPlanDAXGenerator()
    calls = []

    def execute(dax, semantic_model=None):
        calls.append(dax)
        kind = "hasta" if "__hasta" in dax else "valor"
        return {"status": "success", "rows": rows_by_kind[kind]}

    engine._execute_dax = execute
    engine._trace_dax = lambda *args, **kwargs: None
    engine._think = lambda *args, **kwargs: None
    return engine, calls


def test_grouped_empty_result_is_explained_with_the_last_date():
    # Nueva: «visitas por servicio del mes pasado» sin filas (el mes no se ha cargado).
    plan = {**_plan(), "mode": "grouped",
            "group_by": [{"table": "VISITAS", "column": "SERVICIO", "label": "SERVICIO"}]}
    engine, calls = _engine_with({"valor": [], "hasta": [{"[__hasta]": "2026-09-30T00:00:00"}]})
    result = engine._execute_query_plan(plan)
    assert result["status"] == "empty_result", result
    assert result["metric"] == "Total Visitas" and result["data_until"] == "2026-09-30", result
    text = format_empty_result(result)
    assert "no devolvió filas" not in text and "30/09/2026" in text, text
    assert len(calls) == 2, calls


def test_last_date_inside_the_period_is_not_claimed():
    # Nueva: hay datos hasta el 15/10 pero no con el filtro pedido: no se dice «hasta el ...».
    engine, _ = _engine_with({"valor": [{"[__value]": None}], "hasta": [{"[__hasta]": "2026-10-15"}]})
    result = engine._execute_query_plan(_plan())
    assert result["status"] == "empty_result" and not result.get("data_until"), result
    # Ningún dato en ningún periodo: se dice.
    engine, _ = _engine_with({"valor": [], "hasta": [{"[__hasta]": None}]})
    result = engine._execute_query_plan(_plan())
    assert result.get("data_until_none") and "ningún periodo" in empty_result_sentence(result), result


# ------------------------------------------------------------ 3. filtro de inclusión
def _visual(visual_id, page, values, op="in"):
    condition = {"op": op, "values": values} if op == "in" else {"op": "not", "arg": {"op": "in", "values": values}}
    return {"visual_id": visual_id, "page_display_name": page, "visual_type": "card",
            "filters": {"visual": [{"field": {"kind": "column", "table": "VISITAS", "column": "CLASE"},
                                    "condition": condition, "values": values}],
                        "inherited": {"page": [], "report": []}}}


def _with_visuals(qpb, visuals, extra_metrics):
    saved = {"metrics": qpb.metrics, "_visual_index": qpb.__dict__.get("_visual_index")}
    index = {(qpb_norm(GES), v["visual_id"]): v for v in visuals}
    qpb._visual_index = lambda: index
    qpb.metrics = list(qpb.metrics) + extra_metrics
    qpb.__dict__.pop("_inclusion_tokens_cache", None)
    return saved


def qpb_norm(text):
    from src.semantic.query_plan_builder import normalize_text

    return normalize_text(text)


def _restore_visuals(qpb, saved):
    qpb.metrics = saved["metrics"]
    if saved["_visual_index"] is None:
        qpb.__dict__.pop("_visual_index", None)
    qpb.__dict__.pop("_inclusion_tokens_cache", None)


def _card_metric(metric_id, label, visual_id, page):
    return {"metric_id": metric_id, "label": label, "measure": None, "aliases": [label],
            "source_type": "visual_aggregation", "semantic_model": GES, "report": GES, "reports": [GES],
            "table": "VISITAS", "column": "OID", "aggregation": "Count",
            "dax_expression": f"CALCULATE(COUNT('VISITAS'[OID]), {metric_id})", "validation_status": "approved",
            "appearances": [{"report": GES, "page_display_name": page, "page_name": page, "visual_id": visual_id,
                             "visual_type": "card", "visual_title": None}]}


def test_inclusion_filter_names_the_card():
    qpb = builder()
    neo = _card_metric("neo", "Visitas Bebe", "v_neo", "VISITAS ATENDIDAS")
    adultos = _card_metric("adu", "Recuento de OID", "v_adu", "VISITAS ATENDIDAS")
    visuals = [_visual("v_neo", "VISITAS ATENDIDAS", ["CONSULTA NEONATAL", "URGENCIA NEONATAL", "UCI NEONATAL"]),
               _visual("v_adu", "VISITAS ATENDIDAS", ["CONSULTA NEONATAL", "URGENCIA NEONATAL"], op="not")]
    saved = _with_visuals(qpb, visuals, [neo, adultos])
    try:
        assert qpb._inclusion_filter_tokens(neo) == {"neonatal"}, qpb._inclusion_filter_tokens(neo)
        assert qpb._inclusion_filter_tokens(adultos) == set()        # una exclusión no nombra
        # Nuevas: «visitas neonatales atendidas», «cuántas visitas neonatales atendidas hay».
        for question in ("visitas neonatales atendidas", "cuantas visitas neonatales atendidas hay"):
            found = qpb._qualifier_candidates(question, {}, ["neonatal"], ["visita", "atendida"])
            assert found and found[0]["metric"]["metric_id"] == "neo", (question, found)
        # Una palabra que no es la del filtro no lleva a esa tarjeta.
        assert not [item for item in qpb._qualifier_candidates(
            "visitas pediatricas atendidas", {}, ["pediatrica"], ["visita", "atendida"],
        ) if item["metric"]["metric_id"] == "neo"]
    finally:
        _restore_visuals(qpb, saved)


# ------------------------------------------------------------ 4. página como contexto
VALUES = ["URGENCIA PEDIATRICA", "CONSULTA PEDIATRICA", "HOSPITALIZACION PEDIATRICA", "URGENCIA ADULTOS",
          "CONSULTA ADULTOS", "HOSPITALIZACION ADULTOS"]


def _resolve(qpb, leftover, context, question):
    saved = qpb.__dict__.get("_get_values")
    qpb._get_values = lambda model, table, column: list(VALUES)
    try:
        field = {"semantic_model": GES, "table": "VISITAS", "column": "CLASIFICACION", "aliases": ["clasificacion"]}
        return qpb._resolve_implicit_value(leftover, field, GES, [], question=question, context_tokens=context)
    finally:
        if saved is None:
            qpb.__dict__.pop("_get_values", None)
        else:
            qpb._get_values = saved


def test_page_word_does_not_pick_one_value_of_the_family():
    qpb = builder()
    from src.semantic.query_plan_builder import canonical_token

    urg, hosp = {canonical_token("urgencias")}, {canonical_token("hospitalizacion")}
    # Nuevas: «visitas pediátricas que van hoy en urgencias» (página URGENCIAS) y
    # «visitas pediátricas de hospitalización» (página HOSPITALIZACION).
    out = _resolve(qpb, "pediatricas urgencias", urg, "visitas pediatricas que van hoy en urgencias")
    assert out and out.get("values") == sorted(VALUES[:3]), out
    out = _resolve(qpb, "pediatricas hospitalizacion", hosp, "visitas pediatricas de hospitalizacion")
    assert out and out.get("values") == sorted(VALUES[:3]), out
    # Sin ser la página del indicador, «urgencia pediátrica» es un solo valor.
    out = _resolve(qpb, "urgencia pediatrica", set(), "visitas de urgencia pediatrica")
    assert out and out.get("value") == "URGENCIA PEDIATRICA", out
    # «no pediátricas» no es la familia.
    out = _resolve(qpb, "pediatricas urgencias", urg, "visitas no pediatricas en urgencias")
    assert not (out or {}).get("values"), out


# ------------------------------------------------------------ 5. alias de la dimensión con el nombre del indicador
def test_dimension_alias_that_names_the_metric_is_not_the_header():
    # H24: AREA_SERVICIO tiene el alias «VALOR ESTIMADO» (título «VALOR ESTIMADO POR
    # SERVICIO»). Nuevas: «peso lavado por area de servicio», «peso lavado x area».
    qpb = builder()
    metric = {"label": "PESO LAVADO POR SERVICIO", "aliases": ["PESO LAVADO POR SERVICIO", "PESO LAVADO"],
              "semantic_model": GES, "table": "LAVANDERIA"}
    field = {"semantic_model": GES, "table": "LAVANDERIA", "column": "AREA_SERVICIO",
             "aliases": ["PESO LAVADO", "AREA_SERVICIO"]}
    saved = qpb.__dict__.get("_column_business_names")
    qpb._column_business_names = lambda model, column, table=None: ["PESO LAVADO"]
    try:
        assert qpb._group_label(field, metric) == "AREA SERVICIO", qpb._group_label(field, metric)
        # Sin indicador (comportamiento anterior) o con un alias propio de la dimensión, igual que antes.
        assert qpb._group_label(field) == "PESO LAVADO"
        named = {**field, "aliases": ["AREA DE SERVICIO", "PESO LAVADO"]}
        assert qpb._group_label(named, metric) == "AREA DE SERVICIO"
    finally:
        if saved is None:
            qpb.__dict__.pop("_column_business_names", None)
        else:
            qpb._column_business_names = saved


TESTS = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]


def main():
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} pruebas correctas")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
