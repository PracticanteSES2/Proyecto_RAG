"""
Ronda 2 del banco real (segunda parte), offline con un catálogo mínimo:

  BH09  «cuántos pacientes hay hospitalizados en este momento»: la tarjeta
        PACIENTES HOSPITALIZADOS de la página URGENCIAS (tabla «Ingresos de ayer
        a urgencias...») es de un subservicio que la pregunta no nombra; se
        prefiere el indicador general del tablero (TOTAL PACIENTES en INICIO).
  BH18  agrupar por especialidad dejó 40 de 41 pacientes «(sin especialidad)»:
        la fuente no sirve para esa dimensión; se busca otra del tema o se dice.

Ejecutar:  python -m tests.resolution.test_r2_indicador_2
"""
import json
import sys
import tempfile
import traceback
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.query_engine import QueryEngine  # noqa: E402
from src.semantic.query_plan_builder import QueryPlanBuilder  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from tests.resolution.test_resolution import _source  # noqa: E402

BRIEF = "BRIEFING HOSPITALARIO"


def _metric(metric_id, label, table, dax, page, visual_type="card"):
    return {
        "metric_id": metric_id, "label": label, "measure": None, "aliases": [label],
        "source_type": "visual_aggregation", "semantic_model": BRIEF, "report": BRIEF, "reports": [BRIEF],
        "table": table, "column": "X", "aggregation": "DistinctCount", "dax_expression": dax,
        "validation_status": "approved",
        "appearances": [{"report": BRIEF, "page_display_name": page, "page_name": page,
                         "visual_id": f"v_{metric_id}", "visual_title": None, "visual_type": visual_type}],
    }


METRICS = [
    _metric("hosp", "PACIENTES HOSPITALIZADOS", "PACIENTES HOSPITALIZADOS",
            "DISTINCTCOUNT('PACIENTES HOSPITALIZADOS'[PACNUMDOC])", "URGENCIAS"),
    _metric("obs", "PACIENTES OBSERVADOS", "PACIENTES OBSERVADOS",
            "DISTINCTCOUNT('PACIENTES OBSERVADOS'[PACNUMDOC])", "URGENCIAS"),
    _metric("total", "TOTAL PACIENTES", "PACIENTES X ASEGURADORA",
            "DISTINCTCOUNT('PACIENTES X ASEGURADORA'[ADNINGRESO])", "INICIO"),
    # También en INICIO, pero no son «los pacientes del hospital»: una cuenta
    # interconsultas (su tabla habla de pacientes) y otra los de la emergencia
    # del sismo (además está en su propia página PACIENTES EMERGENCIA).
    _metric("inter", "INTERCONSULTAS SIN RESPUESTA", "INTERCONSULTAS",
            "DISTINCTCOUNT('INTERCONSULTAS'[OID])", "INICIO"),
    {**_metric("emerg", "TOTAL DE PACIENTES", "PACIENTES EMERGENCIA",
               "DISTINCTCOUNT('PACIENTES EMERGENCIA'[DOCUMENTO])", "INICIO"),
     "appearances": [
         {"report": BRIEF, "page_display_name": page, "page_name": page, "visual_id": f"v_emerg_{page}",
          "visual_title": None, "visual_type": "card"} for page in ("INICIO", "PACIENTES EMERGENCIA")]},
]

TECHNICAL = {"semantic_model": BRIEF, "relationships": [], "tables": [
    {"name": "PACIENTES HOSPITALIZADOS", "measures": [], "columns": [
        {"name": "PACNUMDOC", "data_type": "String"}, {"name": "GASNOMBRE", "data_type": "String"}]},
    {"name": "PACIENTES OBSERVADOS", "measures": [], "columns": [{"name": "PACNUMDOC", "data_type": "String"}]},
    {"name": "INTERCONSULTAS", "measures": [], "columns": [{"name": "OID", "data_type": "Int64"}]},
    {"name": "PACIENTES EMERGENCIA", "measures": [], "columns": [{"name": "DOCUMENTO", "data_type": "String"}]},
    {"name": "PACIENTES X ASEGURADORA", "measures": [], "columns": [
        {"name": "ADNINGRESO", "data_type": "Int64"}, {"name": "ESPECIALIDAD", "data_type": "String"},
        {"name": "HSUNOMBRE", "data_type": "String"}]},
]}

DICTIONARY = {"semantic_model": BRIEF, "dashboards": [{
    "name": "DICCIONARIO BRIEFING", "is_dictionary": True,
    "data_sources": [
        "PACIENTES HOSPITALIZADOS: Ingresos de ayer a urgencias o ginecología con tipo de ingreso 2. Origen: SQL.",
        "PACIENTES OBSERVADOS: Ingresos de ayer a urgencias o ginecología con tipo de ingreso 1. Origen: SQL.",
        "PACIENTES X ASEGURADORA: Camas ocupadas con ingreso, paciente, servicio y aseguradora. Origen: SQL.",
        "INTERCONSULTAS: Interconsultas de los pacientes con folio y especialidad. Origen: SQL.",
        "PACIENTES EMERGENCIA: Pacientes atendidos en la emergencia del movimiento telúrico. Origen: Excel.",
    ],
}]}


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    source = _source("brief", BRIEF, BRIEF, ["briefing"])
    files = {
        catalog / "source_registry.json": {
            "models": [{"semantic_model": BRIEF, "semantic_model_key": "brief",
                        "technical_catalog": source["technical_catalog"]}],
            "sources": [source]},
        rag / "visual_metrics_catalog.json": {"schema_version": 2, "reports": []},
        rag / "master_metrics.json": {"metrics": METRICS},
        catalog / "brief_rag.json": TECHNICAL,
        root / "data" / "semantic_documents" / "brief" / "md" / "_diccionario.json": DICTIONARY,
    }
    for path, data in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class FakeProvider:
    def execute_dax(self, dax, semantic_model=None):
        return {"status": "success", "rows": []}


_STATE = {}


def builder():
    if "builder" not in _STATE:
        tmp = tempfile.TemporaryDirectory()
        _STATE["tmp"] = tmp
        root = Path(tmp.name)
        _build_fixture(root)
        router = SourceModelRouter(root / "data" / "catalog" / "source_registry.json",
                                   root / "data" / "rag" / "visual_metrics_catalog.json", project_root=root)
        _STATE["builder"] = QueryPlanBuilder(
            root / "data" / "rag" / "master_metrics.json", root / "data" / "rag" / "visual_metrics_catalog.json",
            router, FakeProvider(), project_root=root, today=date(2026, 10, 30),
        )
    return _STATE["builder"]


def resolve(question):
    qpb = builder()
    return qpb._resolve_metric_flexible(question, qpb._source_context(question))


# ---------------------------------------------------------------- BH09
def test_subservice_card_gives_way_to_the_general_indicator():
    resolution = resolve("cuantos pacientes hay hospitalizados en este momento")
    assert resolution.get("status") == "resolved", resolution.get("status")
    assert resolution["metric"]["metric_id"] == "total", resolution["metric"]["label"]
    assert resolution.get("general_indicator")


def test_plan_uses_the_general_indicator_without_pending_words():
    plan = builder().build("cuantos pacientes hay hospitalizados en este momento")
    metric = plan.get("metric") or (plan.get("metric_resolution") or {}).get("metric") or {}
    assert metric.get("metric_id") == "total", (plan.get("status"), plan.get("reason"), metric.get("label"))
    assert "hospitalizados" not in " ".join(plan.get("unapplied_terms") or []), plan.get("unapplied_terms")


def test_subservice_named_in_the_question_keeps_its_card():
    resolution = resolve("cuantos pacientes hospitalizados hay en urgencias")
    assert resolution.get("status") == "resolved" and resolution["metric"]["metric_id"] == "hosp", (
        resolution.get("status"), (resolution.get("metric") or {}).get("label"))


def test_specific_qualifier_the_general_indicator_does_not_explain_is_kept():
    resolution = resolve("cuantos pacientes observados hay")
    assert resolution.get("status") == "resolved" and resolution["metric"]["metric_id"] == "obs", (
        resolution.get("status"), (resolution.get("metric") or {}).get("label"))


# ---------------------------------------------------------------- BH18
class _Builder:
    def __init__(self, alternative=None):
        self.alternative = alternative
        self.calls = []

    def blank_group_alternative(self, plan, share):
        self.calls.append(share)
        return self.alternative


def _engine(alternative=None):
    engine = object.__new__(QueryEngine)
    engine._trace = None
    engine.query_plan_builder = _Builder(alternative)
    return engine


PLAN = {
    "question": "que especialidades se manejan en urgencias y cuantos pacientes tiene cada una",
    "mode": "grouped",
    "metric": {"label": "CANTIDAD DE PACIENTES", "metric_id": "m"},
    "group_by": [{"table": "PACIENTES X ASEGURADORA", "column": "ESPECIALIDAD", "label": "ESPECIALIDAD",
                  "aliases": ["especialidad"]}],
}
ROWS = [
    {"PACIENTES X ASEGURADORA[ESPECIALIDAD]": None, "[__value]": 40},
    {"PACIENTES X ASEGURADORA[ESPECIALIDAD]": "ORTOPEDIA Y TRAUMATOLOGIA", "[__value]": 1},
]


def test_mostly_blank_grouping_is_detected():
    engine = _engine()
    blank = engine._mostly_blank_group(PLAN, ROWS)
    assert blank is not None and round(blank["share"], 3) == round(40 / 41, 3), blank
    rows = [{"X[ESPECIALIDAD]": "A", "[__value]": 10}, {"X[ESPECIALIDAD]": "", "[__value]": 3}]
    assert engine._mostly_blank_group(PLAN, rows) is None
    # Una agrupación temporal no se juzga así.
    temporal = {**PLAN, "group_by": [{**PLAN["group_by"][0], "temporal": "month"}]}
    assert engine._mostly_blank_group(temporal, ROWS) is None


def test_without_another_source_the_user_is_told_instead_of_a_blank_table():
    engine = _engine(alternative=None)
    blank = engine._mostly_blank_group(PLAN, ROWS)
    result = engine._blank_group_response(PLAN, ROWS, blank, {"dax": "EVALUATE ..."}, {"status": "success"})
    assert result["result_type"] == "message", result
    assert "en blanco en 40 de 41" in result["answer"], result["answer"]
    assert "ORTOPEDIA Y TRAUMATOLOGIA (1)" in result["answer"], result["answer"]
    assert engine.query_plan_builder.calls, "debe buscar otra fuente antes de rendirse"


def test_another_source_of_the_same_topic_is_used():
    alternative = {"status": "ready", "mode": "grouped"}
    engine = _engine(alternative=alternative)
    executed = []
    engine._execute_query_plan = lambda plan: executed.append(plan) or {"status": "success", "from": "otra"}
    blank = engine._mostly_blank_group(PLAN, ROWS)
    result = engine._blank_group_response(PLAN, ROWS, blank, {}, {})
    assert result == {"status": "success", "from": "otra"} and executed[0].get("blank_group_retry")


def test_planner_without_sibling_returns_none():
    qpb = builder()
    plan = {**PLAN, "metric": METRICS[2], "source_context": {}}
    assert qpb.blank_group_alternative(plan, 40 / 41) is None


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
