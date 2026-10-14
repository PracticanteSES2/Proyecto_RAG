"""
Elección del indicador y alcance de la pregunta (prueba con usuarios del
hospital, 2026-10-14), offline con un catálogo mínimo:

  BRIEFING (tabla CAMAS DISPONIBLES: HCACODIGO, SERVICIOS, ESTADOS_CAM, OCUPADAS)
      %OCUPACION     = DIVIDE(SUM(OCUPADAS), DISTINCTCOUNT(HCACODIGO)), visual «%OCUPACIÓN» (INICIO, GESTIÓN CAMAS)
      CamasFiltradas = DISTINCTCOUNT(HCACODIGO), en el MISMO visual «%OCUPACIÓN» (alias compartido)
      CAMAS          = COUNT(HCACODIGO) (GESTIÓN CAMAS)
  DEMANDA (tabla SOLICITUD_CAMAS: SERVICIO_SOLICITADO, DEMANDA_INS)
      HOSPITALIZACIÓN = SUM(DEMANDA_INS) (demanda insatisfecha de camas)
  Valores documentados (_documented_values.json): ESTADOS_CAM = DISPONIBLE/OCUPADA/BLOQUEADA y
  SOLICITUD CAMAS[SERVICIO_SOLICITADO] = HOSPITALIZACIÓN GENERAL / UCI ADULTOS.

1. Nombre propio frente a alias compartido: «ocupación general» es %OCUPACION
   sin contrapregunta (CamasFiltradas solo coincide por el título del visual).
2. Alcance: «en el hospital», «general», «institucional» no son filtros, no
   quedan como «No pude aplicar» y no exploran valores de columnas; una
   palabra genérica sola no elige un valor de varias palabras.
3. «cuántas camas ...»: gana el indicador que cuenta camas; la palabra que es
   parte de un valor documentado («hospitalización general») es un filtro.
4. «disponibles» nombra la tabla CAMAS DISPONIBLES y además es el valor
   DISPONIBLE de ESTADOS_CAM: se filtra.

Ejecutar:  python -m tests.resolution.test_indicador      (o pytest tests/resolution)
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

from src.semantic.query_plan_builder import QueryPlanBuilder  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from tests.resolution.test_resolution import _column, _source  # noqa: E402

BRIEF, DEM = "BRIEFING", "DEMANDA INSATISFECHA"
CAMAS_T, SOL_T = "CAMAS DISPONIBLES", "SOLICITUD_CAMAS"
SERVICIOS = ["HOSPITALIZACIÓN GENERAL", "HOSPITALIZACIÓN INTERMEDIOS", "UCI ADULTOS", "PEDIATRÍA"]
ESTADOS = ["BLOQUEADA", "DISPONIBLE", "OCUPADA"]
DOMAINS = {
    (BRIEF, CAMAS_T, "SERVICIOS"): SERVICIOS,
    (BRIEF, CAMAS_T, "ESTADOS_CAM"): ESTADOS,
    (DEM, SOL_T, "SERVICIO_SOLICITADO"): ["HOSPITALIZACIÓN GENERAL", "UCI ADULTOS"],
}
OCUPACION_DAX = (
    "DIVIDE(SUM('CAMAS DISPONIBLES'[OCUPADAS]), DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO]))"
)


def _metric(metric_id, model, label, table, expression, pages=(), title=None):
    return {
        "metric_id": metric_id, "label": label, "measure": label,
        "aliases": [label, *([title] if title else []), f"{table}.{label}"],
        "semantic_model": model, "report": model, "reports": [model],
        "table": table, "dax_expression": f"[{label}]", "model_expression": expression,
        "validation_status": "approved",
        "appearances": [
            {"report": model, "page_display_name": page, "visual_id": f"{metric_id}_{i}",
             "visual_title": title or label}
            for i, page in enumerate(pages)
        ],
    }


METRICS = [
    _metric("b_ocupacion", BRIEF, "%OCUPACION", CAMAS_T, OCUPACION_DAX,
            pages=["INICIO", "GESTIÓN CAMAS"], title="%OCUPACIÓN"),
    _metric("b_filtradas", BRIEF, "CamasFiltradas", CAMAS_T,
            "DISTINCTCOUNT('CAMAS DISPONIBLES'[HCACODIGO])", pages=["INICIO"], title="%OCUPACIÓN"),
    _metric("b_camas", BRIEF, "CAMAS", CAMAS_T, "COUNT('CAMAS DISPONIBLES'[HCACODIGO])",
            pages=["GESTIÓN CAMAS"]),
    _metric("d_hosp", DEM, "HOSPITALIZACIÓN", SOL_T, "SUM('SOLICITUD_CAMAS'[DEMANDA_INS])",
            pages=["CONSOLIDADO"]),
]


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    sources = [
        _source("brief", BRIEF, BRIEF, ["briefing hospitalario"]),
        _source("dem", DEM, DEM, ["demanda insatisfecha"]),
    ]
    registry = {
        "models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                    "technical_catalog": s["technical_catalog"]} for s in sources],
        "sources": sources,
    }
    technical = {
        "brief": {"semantic_model": BRIEF, "relationships": [], "tables": [
            {"name": CAMAS_T, "columns": [
                {"name": "HCACODIGO", "data_type": "String"}, {"name": "SERVICIOS", "data_type": "String"},
                {"name": "ESTADOS_CAM", "data_type": "String"}, {"name": "OCUPADAS", "data_type": "Int64"}],
             "measures": [{"name": m["label"], "expression": m["model_expression"]}
                          for m in METRICS if m["semantic_model"] == BRIEF]}]},
        "dem": {"semantic_model": DEM, "relationships": [], "tables": [
            {"name": SOL_T, "columns": [
                {"name": "SERVICIO_SOLICITADO", "data_type": "String"},
                {"name": "DEMANDA_INS", "data_type": "Int64"}],
             "measures": [{"name": "HOSPITALIZACIÓN", "expression": "SUM('SOLICITUD_CAMAS'[DEMANDA_INS])"}]}]},
    }
    visuals = {"schema_version": 2, "reports": [
        {"report": BRIEF, "semantic_model": BRIEF, "source_group": "brief", "pages": [
            {"page_name": "p1", "page_display_name": "GESTIÓN CAMAS", "filters": {}, "visuals": [
                {"visual_id": "matriz", "visual_type": "pivotTable",
                 "fields": [_column(CAMAS_T, "SERVICIOS"), _column(CAMAS_T, "ESTADOS_CAM")]}]}]},
        {"report": DEM, "semantic_model": DEM, "source_group": "dem", "pages": [
            {"page_name": "p2", "page_display_name": "CONSOLIDADO", "filters": {}, "visuals": [
                {"visual_id": "serv", "visual_type": "slicer",
                 "fields": [_column(SOL_T, "SERVICIO_SOLICITADO")]}]}]},
    ]}
    documented = {
        "briefing": {"semantic_model": BRIEF, "columns": [
            {"table": CAMAS_T, "column": "ESTADOS_CAM", "values": ESTADOS},
            {"table": "SOLICITUD CAMAS", "column": "SERVICIO_SOLICITADO",
             "values": ["HOSPITALIZACIÓN GENERAL", "UCI ADULTOS"]}]},
        "demanda": {"semantic_model": DEM, "columns": [
            {"table": "SOLICITUD CAMAS", "column": "SERVICIO_SOLICITADO",
             "values": ["HOSPITALIZACIÓN GENERAL", "UCI ADULTOS"]}]},
    }
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
    """execute_dax para los VALUES(...) del builder; cuenta las consultas."""

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
        _STATE["provider"] = FakeProvider()
        _STATE["builder"] = QueryPlanBuilder(
            root / "data" / "rag" / "master_metrics.json",
            root / "data" / "rag" / "visual_metrics_catalog.json",
            router, _STATE["provider"], project_root=root,
        )
    return _STATE["builder"]


def metric(metric_id):
    return next(item for item in METRICS if item["metric_id"] == metric_id)


def categorical(plan):
    return {
        (item["column"], str(item["value"]))
        for item in plan.get("filters", []) if item.get("type") == "categorical"
    }


def notes(plan):
    return " | ".join(plan.get("resolution_notes") or [])


# ---------------------------------------------------------------- 1. nombre propio frente a alias
def test_own_name_beats_alias_shared_by_the_visual():
    qpb = builder()
    for question in ("necesito saber la ocupación general hoy en el hospital", "ocupacion general"):
        resolution = qpb._resolve_metric(question, qpb._source_context(question))
        assert resolution["status"] == "resolved", (question, resolution["status"])
        assert resolution["metric"]["metric_id"] == "b_ocupacion", resolution["metric"]["label"]
    plan = qpb.build("necesito saber la ocupación general en el hospital")
    assert plan["status"] == "ready", (plan["status"], plan.get("reason"))
    assert plan["metric"]["metric_id"] == "b_ocupacion"
    assert "CamasFiltradas coincidió solo por «%OCUPACIÓN»" in notes(plan), notes(plan)


def test_alias_that_explains_more_of_the_question_still_competes():
    """El desempate no quita una opción cuyo alias es compartido pero cuya
    tabla/página explica otra palabra de la pregunta («inicio»)."""
    qpb = builder()
    tied = [
        {"metric": metric("b_ocupacion"), "business_score": 0.9, "matched_name": "%OCUPACION",
         "_own_name": True},
        {"metric": metric("b_filtradas"), "business_score": 0.9, "matched_name": "%OCUPACIÓN",
         "_own_name": False, "_shared_alias": True},
    ]
    assert [i["metric"]["metric_id"] for i in qpb._break_metric_tie("ocupacion general", tied)] == ["b_ocupacion"]
    camas = dict(metric("b_filtradas"), table="CAMAS URGENCIAS")
    tied[1]["metric"] = camas
    kept = qpb._break_metric_tie("ocupacion de urgencias", tied)
    assert len(kept) == 2, [i["metric"]["label"] for i in kept]


# ---------------------------------------------------------------- 2. alcance «todo el hospital»
def test_scope_words_are_not_filters_nor_explored():
    qpb = builder()
    provider = _STATE["provider"]
    before = len(provider.queries)
    plan = qpb.build("necesito saber la ocupación general en el hospital")
    assert plan["status"] == "ready", plan["status"]
    assert not categorical(plan), categorical(plan)
    assert not plan["unapplied_terms"], plan["unapplied_terms"]
    assert len(provider.queries) == before, provider.queries[before:]  # sin explorar valores
    assert "se refiere a todo el hospital" in notes(plan), notes(plan)


def test_scope_words_detection():
    qpb = builder()
    ocupacion, camas = metric("b_ocupacion"), metric("b_camas")
    assert qpb._scope_words("necesito saber la ocupacion general hoy en el hospital", ocupacion) == [
        "general", "hospital"]
    assert qpb._scope_words("ocupacion institucional", ocupacion) == ["institucional"]
    assert qpb._scope_words("ocupacion de la clinica hoy", ocupacion) == ["clinica"]
    assert qpb._scope_words("cuantas camas hay en total", camas) == ["total"]
    # Parte de un valor: «hospitalización general», «hospital día».
    assert qpb._scope_words("cuantas camas hay en hospitalizacion general", camas) == []
    assert qpb._scope_words("camas del hospital dia", camas) == []


def test_generic_word_alone_does_not_pick_a_multiword_value():
    qpb = builder()
    value = ["hospitalizacion", "general"]
    assert qpb._generic_partial_value(["general"], value, "ocupacion general hoy")
    assert not qpb._generic_partial_value(["general"], value, "ocupacion en hospitalizacion general")
    assert not qpb._generic_partial_value(["pediatria"], ["pediatria"], "ocupacion de pediatria")
    plan = qpb.build("ocupacion general", selected_metric_id="b_ocupacion")
    assert ("SERVICIOS", "HOSPITALIZACIÓN GENERAL") not in categorical(plan), categorical(plan)


# ---------------------------------------------------------------- 3. sustantivo contado y valores
def test_counted_noun_and_value_phrase_pick_the_beds_measure():
    qpb = builder()
    plan = qpb.build("cuántas camas hay disponibles en hospitalización general")
    assert plan["status"] == "ready", (plan["status"], plan.get("reason"))
    assert plan["metric"]["metric_id"] == "b_camas", plan["metric"]["label"]
    assert categorical(plan) == {("SERVICIOS", "HOSPITALIZACIÓN GENERAL"), ("ESTADOS_CAM", "DISPONIBLE")}, \
        categorical(plan)
    assert not plan["unapplied_terms"], plan["unapplied_terms"]
    assert qpb._counted_noun("cuantas camas hay disponibles") == "cama"
    assert qpb._counted_noun("cuantos pacientes hay") is None  # unidad genérica
    assert qpb._metric_counts(metric("b_camas"), "cama")
    assert qpb._metric_counts(metric("b_filtradas"), "cama")  # DISTINCTCOUNT sobre CAMAS DISPONIBLES
    assert not qpb._metric_counts(metric("d_hosp"), "cama")  # SUM de la demanda


def test_name_inside_a_documented_value_is_a_filter_not_the_metric():
    qpb = builder()
    item = {"metric": metric("d_hosp"), "matched_name": "HOSPITALIZACIÓN"}
    assert qpb._name_inside_value_phrase("camas en hospitalizacion general", item) == "HOSPITALIZACIÓN GENERAL"
    assert qpb._name_inside_value_phrase("demanda de hospitalizacion", item) is None
    tied = [
        {"metric": metric("d_hosp"), "business_score": 1.1, "matched_name": "HOSPITALIZACIÓN", "_own_name": True},
        {"metric": metric("b_camas"), "business_score": 1.1, "matched_name": "CAMAS", "_own_name": True},
    ]
    kept = qpb._break_metric_tie("camas en hospitalizacion general", tied)
    assert [i["metric"]["metric_id"] for i in kept] == ["b_camas"], [i["metric"]["label"] for i in kept]


# ---------------------------------------------------------------- 4. palabra de la tabla = valor
def test_table_word_that_is_a_documented_value_is_filtered():
    qpb = builder()
    plan = qpb.build("cuántas camas hay disponibles en hospitalización general", selected_metric_id="b_camas")
    assert ("ESTADOS_CAM", "DISPONIBLE") in categorical(plan), categorical(plan)
    assert "«disponibles» nombra la tabla CAMAS DISPONIBLES" in notes(plan), notes(plan)
    # Si la palabra es parte del NOMBRE del indicador, la medida ya la explica.
    named = dict(metric("b_camas"), label="Camas disponibles", measure="Camas disponibles", appearances=[])
    assert qpb._table_word_filters(named, ["disponibles"], [], set(), BRIEF) == []
    # Una palabra de la tabla que no es un valor documentado no se filtra.
    assert qpb._table_word_filters(metric("b_camas"), ["camas"], [], set(), BRIEF) == []


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
