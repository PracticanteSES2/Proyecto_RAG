"""
Elección del indicador, ronda 2 (variantes de las preguntas del hospital,
2026-10-14), offline con un catálogo mínimo:

  BRIEFING  CAMAS (COUNT de 'CAMAS DISPONIBLES'[HCACODIGO], visible) y CAMAS OCUPADAS
            (SUM de 'GESTIÓN CAMAS'[PACIENTE_ACOSTADO], tabla sin servicio)
  ATENCIONES CAMAS_DISPONIBLES (capacidad × días, medida auxiliar sin visual)
  FARMACIA  tarjetas «0-30 DÍAS» y «30-120 DÍAS»: la misma DISTINCTCOUNT con distinto
            filtro de visual (mes <= 1 / mes IN {2, 3, 4})
  CITAS     %INASISTENCIA (DIVIDE); URGENCIAS TIEMPO PROMEDIO PARA ATENCIÓN EN TRIAGE
  FACTURACION TOTAL FACTURACION (SUM de MONTO_FACTURADO) y DIAS EN PROCESO (SUM de días)

1. Filtros de nivel de visual: la condición de PBIR se traduce a DAX y la
   tarjeta la lleva en su expresión.
2. «porcentaje/promedio/total...» los explica un indicador de ese tipo.
3. «vencen» explica VENCIMIENTO (no «vencidos») y «30 días» cubre «0-30 DÍAS».
4. Sumas de dinero se marcan como currency.
5. Medida auxiliar frente a indicador visible; candidato que sí filtra.
6. «por eps» no nombra el TABLERO EPS; nombre exacto corto -> dato.

Ejecutar:  python -m tests.resolution.test_indicador2
"""
import json
import sys
import tempfile
import traceback
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.semantic.query_plan_builder import (  # noqa: E402
    QueryPlanBuilder, _phrase_score, _tokens_match_loosely,
)
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from src.semantic.visual_filters import (  # noqa: E402
    describe_condition, filter_dax, parse_condition,
)
from tests.resolution.test_resolution import _column, _source  # noqa: E402

BRIEF, ATEN, FARM, CITAS, URG, FAC = (
    "BRIEFING", "ATENCIONES", "FARMACIA", "CITAS", "URGENCIAS", "FACTURACION",
)
CAMAS_T, GESTION_T, VENC_T = "CAMAS DISPONIBLES", "GESTIÓN CAMAS", "VENCIMIENTO_PRODUCTOS"
DOMAINS = {
    (BRIEF, CAMAS_T, "SERVICIOS"): ["HOSPITALIZACIÓN GENERAL", "UCI ADULTOS", "PEDIATRÍA"],
    (BRIEF, CAMAS_T, "ESTADOS_CAM"): ["BLOQUEADA", "DISPONIBLE", "OCUPADA"],
}


def _metric(metric_id, model, label, table, expression, pages=(), source_type="explicit_measure",
            visual_ids=None):
    return {
        "metric_id": metric_id, "label": label,
        "measure": label if source_type == "explicit_measure" else None,
        "aliases": [label, f"{table}.{label}"], "source_type": source_type,
        "semantic_model": model, "report": model, "reports": [model], "table": table,
        "dax_expression": expression if source_type != "explicit_measure" else f"[{label}]",
        "model_expression": expression if source_type == "explicit_measure" else None,
        "validation_status": "approved",
        "appearances": [
            {"report": model, "page_display_name": page,
             "visual_id": (visual_ids or {}).get(page, f"{metric_id}_{i}"), "visual_title": None,
             "visual_type": "card"}
            for i, page in enumerate(pages)
        ],
    }


VENC_EXPR = "DISTINCTCOUNT('VENCIMIENTO_PRODUCTOS'[IPRCODIGO])"
METRICS = [
    _metric("b_camas", BRIEF, "CAMAS", CAMAS_T, "COUNT('CAMAS DISPONIBLES'[HCACODIGO])", pages=["GESTIÓN CAMAS"]),
    _metric("b_ocupadas", BRIEF, "CAMAS OCUPADAS", GESTION_T, "SUM('GESTIÓN CAMAS'[PACIENTE_ACOSTADO])",
            pages=["GESTIÓN CAMAS"]),
    _metric("a_disp", ATEN, "CAMAS_DISPONIBLES", "PORCENTAJE_OCUPACIONAL",
            "[NUMERO_CAMAS] * DAY(EOMONTH(MAX('PORCENTAJE_OCUPACIONAL'[FECHADES]), 0))"),
    _metric("f_030", FARM, "MEDICAMENTOS EN VENCIMIENTO 0-30 DÍAS", VENC_T, VENC_EXPR,
            pages=["MEDICAMENTOS VENCIDOS"], source_type="visual_aggregation",
            visual_ids={"MEDICAMENTOS VENCIDOS": "v030"}),
    _metric("f_30120", FARM, "MEDICAMENTOS EN VENCIMIENTO 30-120 DÍAS", VENC_T, VENC_EXPR,
            pages=["MEDICAMENTOS VENCIDOS"], source_type="visual_aggregation",
            visual_ids={"MEDICAMENTOS VENCIDOS": "v30120"}),
    _metric("c_inasist", CITAS, "%INASISTENCIA", "CITAS_ASIGNADAS",
            "CALCULATE((sum(CITAS_ASIGNADAS[Inasistida])/sum(CITAS_ASIGNADAS[Asignada])))", pages=["OFERTA"]),
    _metric("u_triage", URG, "TIEMPO PROMEDIO PARA ATENCIÓN EN TRIAGE", "OPORTUNIDAD_TRIAGE",
            "AVERAGE('OPORTUNIDAD_TRIAGE'[MIN])", pages=["RESUMEN"], source_type="visual_aggregation"),
    _metric("fac_total", FAC, "TOTAL FACTURACION", "FACTURADORES", "SUM('FACTURADORES'[MONTO_FACTURADO])",
            pages=["FACTURADORES"], source_type="visual_aggregation"),
    _metric("fac_dias", FAC, "DIAS EN PROCESO FACTURACION", "ENPROCESO",
            "SUM('ENPROCESO'[DIAS_EN_PROCESO])", pages=["EN PROCESO"], source_type="visual_aggregation"),
]


def _filter(name, table, column, condition):
    return {"scope": "visual", "name": name, "type": "Advanced",
            "field": {"kind": "column", "table": table, "column": column},
            "values": [], "has_condition": True, "condition": condition}


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    keys = {BRIEF: "brief", ATEN: "aten", FARM: "farm", CITAS: "citas", URG: "urg", FAC: "fac"}
    sources = [_source(key, model, model, [model.lower()]) for model, key in keys.items()]
    registry = {
        "models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                    "technical_catalog": s["technical_catalog"]} for s in sources],
        "sources": sources,
    }
    tables = {
        BRIEF: [(CAMAS_T, ["HCACODIGO", "SERVICIOS", "ESTADOS_CAM"]), (GESTION_T, ["PACIENTE_ACOSTADO", "Estado"])],
        FARM: [(VENC_T, ["IPRCODIGO", "mes"])],
    }
    technical = {}
    for model, key in keys.items():
        technical[key] = {"semantic_model": model, "relationships": [], "tables": [
            {"name": name, "columns": [{"name": column, "data_type": "String"} for column in columns],
             "measures": [{"name": m["label"], "expression": m["model_expression"]}
                          for m in METRICS if m["semantic_model"] == model and m["table"] == name
                          and m["model_expression"]]}
            for name, columns in tables.get(model, [])
        ]}
    visuals = {"schema_version": 2, "reports": [
        {"report": BRIEF, "semantic_model": BRIEF, "source_group": "brief", "pages": [
            {"page_name": "p1", "page_display_name": "GESTIÓN CAMAS", "filters": {}, "visuals": [
                {"visual_id": "matriz", "visual_type": "pivotTable",
                 "fields": [_column(CAMAS_T, "SERVICIOS"), _column(CAMAS_T, "ESTADOS_CAM")]}]}]},
        {"report": FARM, "semantic_model": FARM, "source_group": "farm", "pages": [
            {"page_name": "p2", "page_display_name": "MEDICAMENTOS VENCIDOS", "filters": {}, "visuals": [
                {"visual_id": "v030", "visual_type": "card", "fields": [],
                 "filters": {"visual": [_filter("f1", VENC_T, "mes", {"op": "cmp", "cmp": "<=", "value": 1})]}},
                {"visual_id": "v30120", "visual_type": "card", "fields": [],
                 "filters": {"visual": [_filter("f2", VENC_T, "mes", {"op": "in", "values": [2, 3, 4]})]}},
            ]}]},
    ]}
    documented = {"briefing": {"semantic_model": BRIEF, "columns": [
        {"table": CAMAS_T, "column": "ESTADOS_CAM", "values": ["BLOQUEADA", "DISPONIBLE", "OCUPADA"]}]}}
    files = {
        catalog / "source_registry.json": registry,
        rag / "visual_metrics_catalog.json": visuals,
        rag / "master_metrics.json": {"metrics": METRICS},
        **{catalog / f"{key}_rag.json": value for key, value in technical.items()},
    }
    for slug, payload in documented.items():
        folder = root / "data" / "model_metadata" / slug
        folder.mkdir(parents=True)
        files[folder / "_documented_values.json"] = payload
    for path, data in files.items():
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class FakeProvider:
    def __init__(self):
        self.queries = []

    def execute_dax(self, dax, semantic_model=None):
        self.queries.append(dax)
        compact = dax.replace("\n", "").replace(" ", "")
        rows = []
        for (model, table, column), values in DOMAINS.items():
            if model == semantic_model and f"VALUES('{table}'[{column}])".replace(" ", "") in compact:
                rows = [{"[Value]": value} for value in values]
        return {"status": "success", "rows": rows}


_STATE = {}


def builder():
    if "builder" not in _STATE:
        tmp = tempfile.TemporaryDirectory()
        _STATE["tmp"] = tmp
        root = Path(tmp.name)
        _build_fixture(root)
        router = SourceModelRouter(
            root / "data" / "catalog" / "source_registry.json",
            root / "data" / "rag" / "visual_metrics_catalog.json", project_root=root,
        )
        _STATE["builder"] = QueryPlanBuilder(
            root / "data" / "rag" / "master_metrics.json",
            root / "data" / "rag" / "visual_metrics_catalog.json",
            router, FakeProvider(), project_root=root,
        )
    return _STATE["builder"]


def loaded(metric_id):
    return next(item for item in builder().metrics if item["metric_id"] == metric_id)


def categorical(plan):
    return {(item["column"], str(item["value"])) for item in plan.get("filters", [])
            if item.get("type") == "categorical"}


# ---------------------------------------------------------------- 1. filtros de visual
def test_pbir_condition_is_parsed_and_translated():
    def column(name):
        return {"Column": {"Expression": {"SourceRef": {"Source": "v"}}, "Property": name}}

    lte = {"filter": {"Where": [{"Condition": {"Comparison": {
        "ComparisonKind": 4, "Left": column("mes"), "Right": {"Literal": {"Value": "1L"}}}}}]}}
    condition = parse_condition(lte, "mes")
    assert condition == {"op": "cmp", "cmp": "<=", "value": 1}, condition
    assert filter_dax(VENC_T, "mes", condition) == (
        "KEEPFILTERS(FILTER(ALL('VENCIMIENTO_PRODUCTOS'[mes]), 'VENCIMIENTO_PRODUCTOS'[mes] <= 1))"
    )
    # NOT IN (antes el catálogo solo guardaba el valor y parecía un IN).
    not_in = {"filter": {"Where": [{"Condition": {"Not": {"Expression": {"In": {
        "Expressions": [column("SERVICIO")], "Values": [[{"Literal": {"Value": "'HOSPITALIZACION PARCIAL'"}}]]}}}}}]}}
    condition = parse_condition(not_in, "SERVICIO")
    assert describe_condition(condition, "SERVICIO") == "SERVICIO no es HOSPITALIZACION PARCIAL"
    assert "NOT ('EGRESOS'[SERVICIO] IN {\"HOSPITALIZACION PARCIAL\"})" in filter_dax("EGRESOS", "SERVICIO", condition)
    # En blanco = ISBLANK.
    blank = {"filter": {"Where": [{"Condition": {"Comparison": {
        "ComparisonKind": 0, "Left": column("OID_RESPUESTA"), "Right": {"Literal": {"Value": "null"}}}}}]}}
    assert "ISBLANK('I'[OID_RESPUESTA])" in filter_dax("I", "OID_RESPUESTA", parse_condition(blank, "OID_RESPUESTA"))


def test_card_carries_its_visual_filter():
    card, other = loaded("f_030"), loaded("f_30120")
    assert card["dax_expression"] == (
        "CALCULATE(" + VENC_EXPR + ", KEEPFILTERS(FILTER(ALL('VENCIMIENTO_PRODUCTOS'[mes]), "
        "'VENCIMIENTO_PRODUCTOS'[mes] <= 1)))"
    ), card["dax_expression"]
    assert card["base_dax_expression"] == VENC_EXPR
    assert "IN {2, 3, 4}" in other["dax_expression"], other["dax_expression"]
    # Dos tarjetas con distinto filtro ya no son «la misma medida».
    assert builder()._logical_key(card) != builder()._logical_key(other)
    # Sin filtros de visual, la expresión no cambia.
    assert loaded("b_camas")["dax_expression"] == "[CAMAS]"


# ---------------------------------------------------------------- 2. tipo de dato
def test_measure_type_words_are_explained_by_the_metric_type():
    qpb = builder()
    assert qpb._measure_type_words("porcentaje de inasistencia institucional", loaded("c_inasist")) == ["porcentaje"]
    triage = loaded("u_triage")
    assert qpb._measure_type_words("tiempo promedio de triage", triage) == ["promedio"]
    assert qpb._measure_type_words("porcentaje de triage", triage) == []
    plan = qpb.build("porcentaje de inasistencia institucional")
    assert plan["status"] == "ready" and plan["metric"]["metric_id"] == "c_inasist", plan.get("status")
    assert not plan["unapplied_terms"], plan["unapplied_terms"]


# ---------------------------------------------------------------- 3. derivación y rangos
def test_verb_explains_noun_and_range_is_named_by_its_top():
    assert _tokens_match_loosely("vencen", "vencimiento")
    assert not _tokens_match_loosely("vencido", "vencimiento")  # vencidos != por vencer
    question = "cuantos medicamentos se vencen en los proximos 30 dias"
    near = _phrase_score(question, "MEDICAMENTOS EN VENCIMIENTO 0-30 DÍAS")
    far = _phrase_score(question, "MEDICAMENTOS EN VENCIMIENTO 30-120 DÍAS")
    assert near > far and near >= 0.9, (near, far)
    resolution = builder()._resolve_metric(question, builder()._source_context(question))
    assert resolution["status"] == "resolved" and resolution["metric"]["metric_id"] == "f_030", resolution["status"]


# ---------------------------------------------------------------- 4. dinero
def test_money_sums_are_marked_as_currency():
    assert loaded("fac_total").get("format") == "currency"
    assert not loaded("fac_dias").get("format")      # días, no pesos
    assert not loaded("u_triage").get("format")      # promedio de minutos


# ---------------------------------------------------------------- 5. auxiliar, candidato que filtra
def test_visible_indicator_beats_auxiliary_measure():
    qpb = builder()
    question = "detalle de camas disponibles por servicio"
    resolution = qpb._resolve_metric(question, qpb._source_context(question))
    assert resolution["status"] == "resolved", resolution["status"]
    assert resolution["metric"]["metric_id"] == "b_camas", resolution["metric"]["label"]


def test_candidate_that_applies_the_filter_is_used():
    plan = builder().build("cuantas camas ocupadas hay en uci")
    assert plan["status"] == "ready", (plan["status"], plan.get("reason"), plan.get("unresolved_text"))
    assert plan["metric"]["metric_id"] == "b_camas", plan["metric"]["label"]
    assert categorical(plan) == {("ESTADOS_CAM", "OCUPADA"), ("SERVICIOS", "UCI ADULTOS")}, categorical(plan)
    assert "CAMAS OCUPADAS no entiende «uci»" in " | ".join(plan.get("resolution_notes") or [])


# ---------------------------------------------------------------- 6. tablero por dimensión y nombre exacto
def test_group_word_is_not_the_board_name():
    qpb = builder()
    context = {"board_mentions": [{"phrase": "eps", "name": "TABLERO EPS"}]}
    text, tokens = qpb._strip_board_mentions("tiempo promedio de triage por eps", context)
    assert text == "tiempo promedio de triage por eps" and not tokens, (text, tokens)
    text, tokens = qpb._strip_board_mentions("triages en el tablero eps", context)
    assert "eps" not in text.split() and tokens, (text, tokens)


def test_exact_short_name_asks_for_the_data():
    qpb = builder()
    context = qpb._source_context("x")
    assert qpb._names_indicator_exactly("camas ocupadas", context)                 # etiqueta exacta
    assert qpb._names_indicator_exactly("medicamentos vencidos", context)      # página con indicadores
    assert not qpb._names_indicator_exactly("camas", context)                  # una palabra
    assert not qpb._names_indicator_exactly("que es el porcentaje de camas", context)


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
