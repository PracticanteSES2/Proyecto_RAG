"""
Enrutamiento v2 (offline): preguntas descriptivas, tablero/página nombrado,
agrupación «por X» con columnas del catálogo técnico y valores implícitos
estrictos.

Ejecutar:  python -m tests.routing.test_board_routing   (también lo corre
           python -m tests.routing.test_routing)

Fixture en un directorio temporal, con el SourceModelRouter REAL:

  Atenciones / TABLERO DE ATENCIONES : «Triages» SIN visual (tabla OPORTUNIDAD_TRIAGE
      con CLASIFICACION_TRIAGE, DESCRI_TRIGE, MENORES, FECHA en el catálogo técnico);
      tableros documentados TRIAGE y URGENCIAS.
  Briefing / BRIEFING HOSPITALARIO   : «Triages» con visual (página INICIO; campo
      TRIAGES[DESCRI_TRIGE] mostrado como «CLASIFICACIÓN», valores TRIAGE I..V);
      «Cirugías realizadas» y ASEGURADOR (con un dominio defectuoso: CIRUGIA);
      tablero documentado URGENCIAS.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chatbot.intent_parser import IntentParser  # noqa: E402
from src.semantic.query_plan_builder import QueryPlanBuilder  # noqa: E402
from src.semantic.question_kind import descriptive_phrase  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402

ATE, BRI = "Atenciones", "Briefing"

DOMAINS = {
    (ATE, "OPORTUNIDAD_TRIAGE", "CLASIFICACION_TRIAGE"): ["I", "II", "III", "IV", "V"],
    (ATE, "OPORTUNIDAD_TRIAGE", "DESCRI_TRIGE"): ["TRIAGE I", "TRIAGE II", "TRIAGE III"],
    (ATE, "OPORTUNIDAD_TRIAGE", "MENORES"): ["MAYORES DE EDAD", "MENORES DE EDAD"],
    (BRI, "TRIAGES", "DESCRI_TRIGE"): ["TRIAGE I", "TRIAGE II", "TRIAGE III", "TRIAGE IV", "TRIAGE V"],
    (BRI, "CIRUGIAS", "ASEGURADOR"): ["CIRUGIA", "NUEVA EPS", "SURA"],
    (BRI, "CIRUGIAS", "ESPECIALIDAD"): ["ORTOPEDIA", "UROLOGIA"],
}


class FakeProvider:
    def __init__(self):
        self.queries = []

    def execute_dax(self, dax, semantic_model=None):
        self.queries.append(dax)
        flat = dax.replace("\n", "").replace(" ", "")
        for (model, table, column), values in DOMAINS.items():
            if model == semantic_model and f"VALUES('{table}'[{column}])" in flat:
                return {"status": "success", "rows": [{"[Value]": value} for value in values]}
        return {"status": "success", "rows": [{"[__value]": 7}]}


def _column(table, name, display=None):
    return {"role": "Values", "kind": "column", "table": table, "column": name,
            "display_name": display or name, "native_query_ref": display or name,
            "query_ref": f"{table}.{name}"}


def _metric(metric_id, model, report, label, table, pages=(), titles=()):
    return {
        "metric_id": metric_id, "label": label, "measure": label, "aliases": [label],
        "semantic_model": model, "report": report if pages else None,
        "reports": [report] if pages else [], "table": table,
        "dax_expression": f"[{label}]", "validation_status": "approved",
        "appearances": [
            {"report": report, "page_display_name": page, "visual_id": f"{metric_id}_{i}",
             "visual_title": title}
            for i, (page, title) in enumerate(zip(pages, titles))
        ],
    }


def _build(root):
    catalog = root / "data" / "catalog"
    rag = root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    registry = {
        "models": [
            {"semantic_model": ATE, "semantic_model_key": "ate", "technical_catalog": "data/catalog/ate_rag.json"},
            {"semantic_model": BRI, "semantic_model_key": "bri", "technical_catalog": "data/catalog/bri_rag.json"},
        ],
        "sources": [
            {"source_group": "tablero_atenciones", "report": "TABLERO DE ATENCIONES", "semantic_model": ATE,
             "default_dashboard": "TABLERO DE ATENCIONES", "aliases": ["TABLERO DE ATENCIONES", "ATENCIONES"],
             "technical_catalog": "data/catalog/ate_rag.json"},
            {"source_group": "tablero_briefing", "report": "BRIEFING HOSPITALARIO", "semantic_model": BRI,
             "default_dashboard": "BRIEFING HOSPITALARIO", "aliases": ["BRIEFING HOSPITALARIO"],
             "technical_catalog": "data/catalog/bri_rag.json"},
            # Modelo sin indicadores en el catálogo maestro.
            {"source_group": "tablero_demanda", "report": "DEMANDA INSATISFECHA", "semantic_model": "Demanda",
             "default_dashboard": "DEMANDA INSATISFECHA", "aliases": ["DEMANDA INSATISFECHA"]},
        ],
    }
    technical_ate = {"semantic_model": ATE, "tables": [
        {"name": "OPORTUNIDAD_TRIAGE", "columns": [
            {"name": "RowNumber-XYZ", "data_type": "Int64"},
            {"name": "OID_TRIAGE", "data_type": "Int64"},
            {"name": "GPANOMBRE", "data_type": "String"},
            {"name": "CLASIFICACION_TRIAGE", "data_type": "String"},
            {"name": "DESCRI_TRIGE", "data_type": "String"},
            {"name": "MENORES", "data_type": "String"},
            {"name": "FECHA", "data_type": "DateTime"},
            {"name": "FechaLlegada", "data_type": "DateTime"},
        ], "measures": [{"name": "Triages", "expression": "COUNTROWS(OPORTUNIDAD_TRIAGE)"}]},
    ], "relationships": []}
    technical_bri = {"semantic_model": BRI, "tables": [
        {"name": "TRIAGES", "columns": [{"name": "DESCRI_TRIGE", "data_type": "String"},
                                        {"name": "FECHA", "data_type": "DateTime"}]},
        {"name": "CIRUGIAS", "columns": [{"name": "ASEGURADOR", "data_type": "String"},
                                         {"name": "ESPECIALIDAD", "data_type": "String"}]},
    ], "relationships": []}
    visuals = {"schema_version": 2, "reports": [
        {"report": "BRIEFING HOSPITALARIO", "semantic_model": BRI, "source_group": "tablero_briefing", "pages": [
            {"page_name": "p1", "page_display_name": "INICIO", "filters": {}, "visuals": [
                {"visual_id": "b_tri", "visual_type": "pieChart",
                 "fields": [_column("TRIAGES", "DESCRI_TRIGE", "CLASIFICACIÓN")]},
                {"visual_id": "b_cx", "visual_type": "tableEx",
                 "fields": [_column("CIRUGIAS", "ASEGURADOR"), _column("CIRUGIAS", "ESPECIALIDAD")]},
                {"visual_id": "b_fecha", "visual_type": "slicer", "fields": [_column("TRIAGES", "FECHA")]},
            ]},
        ]},
    ]}
    metrics = [
        _metric("ate_triages", ATE, "TABLERO DE ATENCIONES", "Triages", "OPORTUNIDAD_TRIAGE"),
        _metric("bri_triages", BRI, "BRIEFING HOSPITALARIO", "Triages", "TRIAGES",
                pages=["INICIO"], titles=["Triages"]),
        _metric("bri_cx", BRI, "BRIEFING HOSPITALARIO", "Cirugías realizadas", "CIRUGIAS",
                pages=["INICIO"], titles=["Cirugías realizadas"]),
    ]
    (catalog / "source_registry.json").write_text(json.dumps(registry), encoding="utf-8")
    (catalog / "ate_rag.json").write_text(json.dumps(technical_ate), encoding="utf-8")
    (catalog / "bri_rag.json").write_text(json.dumps(technical_bri), encoding="utf-8")
    (rag / "visual_metrics_catalog.json").write_text(json.dumps(visuals, ensure_ascii=False), encoding="utf-8")
    (rag / "master_metrics.json").write_text(json.dumps({"metrics": metrics}, ensure_ascii=False), encoding="utf-8")
    router = SourceModelRouter(
        catalog / "source_registry.json", visual_catalog_path=rag / "visual_metrics_catalog.json",
        project_root=root,
    )
    router.register_documentation_dashboards([
        ("TRIAGE", "tablero_atenciones"), ("URGENCIAS", "tablero_atenciones"),
        ("URGENCIAS", "tablero_briefing"), ("TRIAGES", "tablero_briefing"),
        ("TRIAGES", "tablero_demanda"), ("CITAS", "grupo_sin_fuente"),
    ])
    provider = FakeProvider()
    builder = QueryPlanBuilder(
        rag / "master_metrics.json", rag / "visual_metrics_catalog.json", router, provider,
        project_root=root,
    )
    return router, builder, provider


_STATE = {}


def system():
    if "system" not in _STATE:
        tmp = tempfile.TemporaryDirectory()
        _STATE["tmp"] = tmp
        _STATE["system"] = _build(Path(tmp.name))
    return _STATE["system"]


def _categorical(plan):
    return [(f["column"], f["value"]) for f in plan.get("filters") or [] if f.get("type") == "categorical"]


# ---------------------------------------------------------------- 1. descriptivas
DESCRIPTIVE = [
    "cuales son los rangos del nedocs", "¿cómo se calcula el porcentaje de ocupación de camas?",
    "como calculan la proyeccion de triages", "que significan los colores del semaforo",
    "para que sirve el tablero de farmacia", "de donde sale el total de cirugias",
    "que filtros tiene el tablero de triage", "qué mide el indicador giro cama",
    "cual es la formula del porcentaje de ocupacion", "dime cuales son los criterios de clasificacion del triage",
]
NUMERIC = [
    "cual es el porcentaje de ocupacion de camas en marzo", "cuantos triages por rangos de edad en 2025",
    "cuantas cirugias de las que son programadas hubo", "total de pacientes en los rangos del nedocs",
    "dame el total de triages del tablero de triage", "triages por clasificacion en 2025 tablero de triage",
    "cuales son los servicios con mas peso", "cuantos pacientes en semaforo rojo",
]


def test_descriptive_phrase_detector():
    for question in DESCRIPTIVE:
        assert descriptive_phrase(question), question
    for question in NUMERIC:
        assert not descriptive_phrase(question), (question, descriptive_phrase(question))


def test_descriptive_questions_are_not_numeric_even_with_numeric_words():
    _, builder, _ = system()
    for question in DESCRIPTIVE:
        assert not builder.looks_numeric(question), question
    assert builder.descriptive_reason("¿cómo se calcula el porcentaje de ocupación?") == "como se calcula"


class _Retriever:
    def __init__(self, dashboards=(), aliases=None):
        self.dashboards = list(dashboards)
        self.dashboard_aliases = dict(aliases or {})

    def search(self, *args, **kwargs):
        return []


def test_intent_parser_sends_descriptive_numeric_words_to_documentation():
    parser = IntentParser(_Retriever())
    assert parser.detect_intent("¿Cómo se calcula el porcentaje de ocupación de camas?") == "general_question"
    assert parser.detect_intent("cuales son los rangos del total nedocs") == "general_question"
    assert parser.detect_intent("¿Cuál es el porcentaje de ocupación de camas en marzo?") == "query_metric"
    assert parser.detect_intent("cuantos triages hubo en 2025") == "query_metric"


def test_intent_parser_does_not_pin_a_short_name_inside_a_longer_alias():
    class Router:
        sources = [{"report": "TABLERO TIEMPOS URGENCIAS",
                    "aliases": ["TABLERO TIEMPOS DE URGENCIAS", "TIEMPOS DE URGENCIAS"]}]
    parser = IntentParser(_Retriever(dashboards=["URGENCIAS", "DATOS HISTÓRICOS"]), source_router=Router())
    assert parser.detect_dashboard("que es el boton azul en tiempos de urgencias") is None
    assert parser.detect_dashboard("que muestra el tablero de urgencias") == "URGENCIAS"


# ---------------------------------------------------------------- 4. tablero nombrado
def test_board_mention_routes_to_the_only_model_with_that_board():
    router, builder, _ = system()
    # Solo Atenciones tiene un tablero llamado «tablero de atenciones».
    context = router.resolve(question="cuantos triages hay en el tablero de atenciones en 2025")
    assert context["status"] == "resolved" and context["routing_strength"] == "strong", context
    assert context["semantic_model"] == ATE, context
    # «triage»: TRIAGE (Atenciones, tal cual) y TRIAGES (Briefing y Demanda, en
    # plural). El router no decide; el builder descarta Demanda (sin
    # indicadores) y desempata por la forma escrita.
    raw = router.resolve(question="triages por clasificacion en 2025 tablero de triage")
    assert raw.get("reason") != "explicit_board_mention"
    assert sorted(raw["board_mention_models"]) == sorted([ATE, BRI, "Demanda"]), raw
    context = builder._source_context("triages por clasificacion en 2025 tablero de triage")
    assert context["status"] == "resolved" and context["routing_strength"] == "strong", context
    assert context["semantic_model"] == ATE and context["dashboard"] == "TRIAGE", context
    assert context["reason"] == "explicit_board_mention" and "como se escribió" in context["board_note"]
    mention = context["board_mentions"][0]
    assert mention["phrase"] == "tablero de triage" and mention["tokens"] == ["triage"], mention


def test_board_named_like_a_service_in_several_models_fixes_nothing():
    router, _, _ = system()
    context = router.resolve(question="cuantos triages hubo en el tablero de urgencias")
    assert context.get("reason") != "explicit_board_mention", context
    assert sorted(context["board_mention_models"]) == [ATE, BRI], context
    # Sin «tablero de ...» la palabra URGENCIAS no es un tablero nombrado.
    assert not router.resolve(question="cuantos triages hubo en urgencias").get("board_mentions")


def test_board_name_without_metrics_is_ignored_when_choosing_the_model():
    # «tablero de triages»: TRIAGES de Briefing y de Demanda (tal cual) y TRIAGE
    # de Atenciones (singular). Demanda no tiene indicadores; entre Briefing y
    # Atenciones gana la forma escrita: Briefing.
    _, builder, _ = system()
    context = builder._source_context("total de triages del tablero de triages")
    assert context["semantic_model"] == BRI and context["routing_strength"] == "strong", context
    # Un grupo de documentación sin fuente registrada no aporta tableros.
    router, _, _ = system()
    assert not router.board_mentions("citas del tablero de citas")[0]["known"]


def test_named_report_keeps_priority_over_pages():
    router, _, _ = system()
    context = router.resolve(question="triages en el tablero de atenciones")
    assert context["semantic_model"] == ATE and context.get("dashboard") is None, context


# ---------------------------------------------------------------- 2. «por X» y palabras del tablero
def test_group_by_technical_column_and_board_words_are_not_values():
    _, builder, _ = system()
    plan = builder.build("triages por clasificacion en 2025 tablero de triage")
    assert plan["status"] == "ready", (plan.get("status"), plan.get("reason"), plan.get("unresolved_text"))
    assert plan["metric"]["metric_id"] == "ate_triages", plan["metric"]["metric_id"]
    assert plan["mode"] == "grouped", plan["mode"]
    assert [g["column"] for g in plan["group_by"]] == ["CLASIFICACION_TRIAGE"], plan["group_by"]
    assert not _categorical(plan), _categorical(plan)  # nada de DESCRI_TRIGE = TRIAGE III
    assert any(f.get("type") == "date_range" and f.get("year") == 2025 for f in plan["filters"]), plan["filters"]
    assert plan["board_mentions"] == ["tablero de triage"]


def test_technical_dimensions_skip_private_and_numeric_columns():
    _, builder, _ = system()
    metric = next(m for m in builder.metrics if m["metric_id"] == "ate_triages")
    unrelated = {"table": "OTRA_TABLA", "column": "SERVICIO", "aliases": ["servicio"],
                 "kind": "column", "relevance_score": 60}
    fields = builder._with_technical_dimensions(metric, [unrelated])
    columns = {f["column"] for f in fields if f.get("technical")}
    assert columns == {"CLASIFICACION_TRIAGE", "DESCRI_TRIGE", "MENORES", "FECHA", "FechaLlegada"}, columns
    # La medida se calcula sobre OPORTUNIDAD_TRIAGE: sus columnas primero; el
    # campo visual de una tabla que no la filtra queda al final.
    assert fields[-1]["column"] == "SERVICIO" and fields[-1]["unrelated_table"], fields[-1]
    llegada = next(f for f in fields if f["column"] == "FechaLlegada")
    assert "fecha" in llegada["aliases"] and builder._is_temporal_field(llegada)
    # OID_TRIAGE no hereda «clasificación» por contener «triage».
    aliases = builder._technical_field_aliases("OID_TRIAGE")
    assert "clasificacion" not in [a.lower() for a in aliases], aliases
    assert "clasificacion" in builder._technical_field_aliases("CLASIFICACION_TRIAGE")


def test_metric_with_visuals_keeps_its_visual_dimensions():
    _, builder, _ = system()
    metric = next(m for m in builder.metrics if m["metric_id"] == "bri_triages")
    candidates = builder._relevant_dimensions(metric)
    assert builder._with_technical_dimensions(metric, candidates) == candidates


def test_period_inside_the_metric_name_is_declared():
    _, builder, _ = system()
    question = "triages de menores de edad en 2025"
    temporal = builder._analyze_periods(question, {"label": "TRIAGES_2025"}, "TRIAGES_2025")
    assert temporal["period"] is None  # el año es parte del nombre del indicador
    note = builder._period_in_metric_note(
        question, temporal, {"label": "TRIAGES_2025"}, {"matched_name": "TRIAGES_2025"},
    )
    assert note and "2025" in note and "no se aplicó" in note, note
    plain = builder._analyze_periods(question, {"label": "Triages"}, "Triages")
    assert builder._period_in_metric_note(question, plain, {"label": "Triages"}, {}) is None


# ---------------------------------------------------------------- 3. valores implícitos estrictos
def test_implicit_value_shared_by_several_values_is_not_applied():
    _, builder, _ = system()
    field = {"table": "TRIAGES", "column": "DESCRI_TRIGE", "display_name": "CLASIFICACIÓN", "kind": "column"}
    decisions = []
    assert builder._resolve_implicit_value("triage", field, BRI, decisions) is None
    assert decisions and "varios valores" in decisions[0], decisions


def test_metric_concept_is_not_an_insurer_value():
    _, builder, _ = system()
    field = {"table": "CIRUGIAS", "column": "ASEGURADOR", "kind": "column"}
    decisions = []
    assert builder._resolve_implicit_value("cirugias", field, BRI, decisions) is None
    assert decisions and "concepto" in decisions[0], decisions
    resolved = builder._resolve_implicit_value("sura", field, BRI)
    assert resolved and resolved["value"] == "SURA" and "ASEGURADOR" in resolved["reason"], resolved


def test_implicit_filter_reason_is_recorded():
    _, builder, _ = system()
    plan = builder.build("cirugias realizadas de ortopedia en el briefing hospitalario")
    assert plan["status"] == "ready", (plan.get("status"), plan.get("unresolved_text"))
    assert _categorical(plan) == [("ESPECIALIDAD", "ORTOPEDIA")], _categorical(plan)
    implicit = [f for f in plan["filters"] if f.get("source") == "query_plan_implicit_value"][0]
    assert "ortopedia" in implicit["reason"] and "ESPECIALIDAD" in implicit["reason"], implicit
    assert any(item.startswith("aplicado:") for item in plan["implicit_decisions"]), plan["implicit_decisions"]


def test_metric_word_never_becomes_an_implicit_value():
    _, builder, _ = system()
    plan = builder.build("cuantas cirugias realizadas hubo en el briefing hospitalario")
    assert plan["status"] == "ready", plan.get("status")
    assert ("ASEGURADOR", "CIRUGIA") not in _categorical(plan), _categorical(plan)


# tests.routing.test_routing importa solo las pruebas (no el fixture).
__all__ = [name for name in list(globals()) if name.startswith("test_")]


def _run_all():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, func in tests:
        try:
            func()
            print("PASS ", name)
        except Exception as error:  # noqa: BLE001
            failed += 1
            print("FAIL ", name, "->", type(error).__name__, error)
    print(f"{len(tests) - failed}/{len(tests)} OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
