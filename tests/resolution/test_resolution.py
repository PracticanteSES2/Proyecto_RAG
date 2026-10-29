"""
Resolución del indicador en QueryPlanBuilder (offline): nombres débiles,
mismo nombre en varios tableros, variantes por año, tablero nombrado,
palabras sin interpretar que son el núcleo de la pregunta y calificativos
(«triages pediátricos», «consultas ambulatorias», «de ortopedia de sura»).

Catálogo mínimo en un directorio temporal + Power BI falso (solo VALUES):

  Modelo Atenciones / Tablero Atenciones : medidas técnicas SIN visual (como
      el modelo real): TOTAL_TRIAGES, TRIAGES_2024/2025, TRIAGES_PEDIATRICOS_2025,
      «2024», IMAGENES, PROMEDIO_MENSUAL; CONSULTAS (tabla CONSULTAS_AMBULATORIAS).
  Modelo Briefing / Tablero Briefing     : TRIAGES, ASIGNADAS (alias técnico
      «REGISTRADO»), PRODUCTOS BAJO MINIMO (alias técnico «CODIGO»).
  Modelo Lavanderia / Tablero Lavanderia : PESO.
  Modelo Qx / Tablero Qx                 : CIRUGIAS PROGRAMADAS, CIRUGIAS REALIZADAS.

Ejecutar:  python -m tests.resolution.test_resolution      (o pytest tests/resolution)
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
    QueryPlanBuilder,
    _is_request_word,
    _stem_token,
    _tokens_match_loosely,
    canonical_token,
)
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402

ATEN, BRIEF, LAV, QX = "Modelo Atenciones", "Modelo Briefing", "Modelo Lavanderia", "Modelo Qx"

DOMAINS = {
    (BRIEF, "TRIAGES", "SERVICIO"): ["PEDIATRIA", "URGENCIAS ADULTOS"],
    (BRIEF, "TRIAGES", "ASEGURADORA"): ["SURA EPS", "SANITAS EPS", "NUEVA EPS"],
    (BRIEF, "TRIAGES", "PACIENTE"): ["PACIENTE SIMULADO 00001", "PACIENTE SIMULADO 00002"],
    (ATEN, "OPORTUNIDAD_TRIAGE", "ESPECIALIDAD"): ["ORTOPEDIA Y TRAUMATOLOGIA", "PEDIATRIA"],
    (QX, "QX", "ESTADO"): ["Paciente Programado", "Paciente Cancelado"],
    (LAV, "LAVANDERIA", "SERVICIO"): ["ANTIFLUIDOS", "URGENCIAS"],
}


def _column(table, name):
    return {"role": "Values", "kind": "column", "table": table, "column": name,
            "display_name": name, "native_query_ref": name, "query_ref": f"{table}.{name}"}


def _metric(metric_id, model, report, label, table, pages=(), aliases=(), visible=True):
    return {
        "metric_id": metric_id, "label": label, "measure": label,
        "aliases": [label, *aliases], "semantic_model": model,
        "report": report if visible else None, "reports": [report] if visible else [],
        "table": table, "dax_expression": f"[{label}]", "validation_status": "approved",
        "appearances": [
            {"report": report, "page_display_name": page, "visual_id": f"{metric_id}_{i}",
             "visual_title": label}
            for i, page in enumerate(pages)
        ] if visible else [],
    }


def _source(group, report, model, aliases):
    return {"source_group": group, "report": report, "semantic_model": model,
            "default_dashboard": "Inicio", "aliases": aliases,
            "technical_catalog": f"data/catalog/{group}_rag.json"}


def _build_fixture(root):
    catalog = root / "data" / "catalog"
    rag = root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    sources = [
        _source("aten", "Tablero Atenciones", ATEN, ["tablero atenciones", "atenciones institucionales"]),
        _source("brief", "Tablero Briefing", BRIEF, ["tablero briefing", "briefing"]),
        _source("lav", "Tablero Lavanderia", LAV, ["tablero lavanderia", "lavanderia"]),
        _source("qx", "Tablero Qx", QX, ["tablero qx"]),
    ]
    registry = {
        "models": [
            {"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
             "technical_catalog": s["technical_catalog"]}
            for s in sources
        ],
        "sources": sources,
    }
    technical = {
        "aten": {"semantic_model": ATEN, "tables": [
            {"name": "OPORTUNIDAD_TRIAGE", "columns": [{"name": "ESPECIALIDAD", "data_type": "String"}]},
            {"name": "Calendario", "columns": [{"name": "Date", "data_type": "DateTime"}]}]},
        "brief": {"semantic_model": BRIEF, "tables": [
            {"name": "TRIAGES", "columns": [
                {"name": "SERVICIO", "data_type": "String"}, {"name": "ASEGURADORA", "data_type": "String"},
                {"name": "PACIENTE", "data_type": "String"}, {"name": "FECHA", "data_type": "DateTime"}]}]},
        "lav": {"semantic_model": LAV, "tables": [
            {"name": "LAVANDERIA", "columns": [{"name": "SERVICIO", "data_type": "String"}]}]},
        "qx": {"semantic_model": QX, "tables": [
            {"name": "QX", "columns": [{"name": "ESTADO", "data_type": "String"}]}]},
    }
    visuals_catalog = {"schema_version": 2, "reports": [
        {"report": "Tablero Briefing", "semantic_model": BRIEF, "source_group": "brief", "pages": [
            {"page_name": "p1", "page_display_name": "Inicio", "filters": {}, "visuals": [
                {"visual_id": "b_serv", "visual_type": "slicer", "fields": [_column("TRIAGES", "SERVICIO")]},
                {"visual_id": "b_aseg", "visual_type": "slicer", "fields": [_column("TRIAGES", "ASEGURADORA")]},
                {"visual_id": "b_pac", "visual_type": "tableEx", "fields": [_column("TRIAGES", "PACIENTE")]},
                {"visual_id": "b_fecha", "visual_type": "slicer", "fields": [_column("TRIAGES", "FECHA")]},
            ]}]},
        {"report": "Tablero Atenciones", "semantic_model": ATEN, "source_group": "aten", "pages": [
            {"page_name": "p2", "page_display_name": "Consultas prioritarias", "filters": {}, "visuals": [
                {"visual_id": "a_esp", "visual_type": "slicer",
                 "fields": [_column("OPORTUNIDAD_TRIAGE", "ESPECIALIDAD")]},
                {"visual_id": "a_fecha", "visual_type": "slicer", "fields": [_column("Calendario", "Date")]},
            ]}]},
        {"report": "Tablero Lavanderia", "semantic_model": LAV, "source_group": "lav", "pages": [
            {"page_name": "p3", "page_display_name": "Inicio", "filters": {}, "visuals": [
                {"visual_id": "l_serv", "visual_type": "slicer", "fields": [_column("LAVANDERIA", "SERVICIO")]},
            ]}]},
        {"report": "Tablero Qx", "semantic_model": QX, "source_group": "qx", "pages": [
            {"page_name": "p4", "page_display_name": "Cirugias", "filters": {}, "visuals": [
                {"visual_id": "q_est", "visual_type": "slicer", "fields": [_column("QX", "ESTADO")]},
            ]}]},
    ]}
    metrics = [
        _metric("a_total_triages", ATEN, "Tablero Atenciones", "TOTAL_TRIAGES", "OPORTUNIDAD_TRIAGE", visible=False),
        _metric("a_triages_2024", ATEN, "Tablero Atenciones", "TRIAGES_2024", "OPORTUNIDAD_TRIAGE", visible=False),
        _metric("a_triages_2025", ATEN, "Tablero Atenciones", "TRIAGES_2025", "OPORTUNIDAD_TRIAGE", visible=False),
        _metric("a_triages_ped", ATEN, "Tablero Atenciones", "TRIAGES_PEDIATRICOS_2025", "OPORTUNIDAD_TRIAGE",
                visible=False),
        _metric("a_2024", ATEN, "Tablero Atenciones", "2024", "CIRUGIAS_ARC", visible=False),
        _metric("a_imagenes", ATEN, "Tablero Atenciones", "IMAGENES", "CONSOLIDADO_IMAGENES", visible=False),
        _metric("a_prom_mensual", ATEN, "Tablero Atenciones", "PROMEDIO_MENSUAL", "CONSULTAS PRIORITARIAS",
                pages=["Consultas prioritarias"]),
        _metric("a_consultas", ATEN, "Tablero Atenciones", "CONSULTAS", "CONSULTAS_AMBULATORIAS",
                pages=["Consultas prioritarias"]),
        _metric("b_triages", BRIEF, "Tablero Briefing", "TRIAGES", "TRIAGES", pages=["Inicio"]),
        _metric("b_asignadas", BRIEF, "Tablero Briefing", "ASIGNADAS", "CITAS", pages=["Inicio"],
                aliases=["Suma de REGISTRADO", "REGISTRADO"]),
        _metric("b_productos", BRIEF, "Tablero Briefing", "PRODUCTOS BAJO MINIMO", "CANTIDAD_MINIMA",
                pages=["Inicio"], aliases=["Conteo distinto de CODIGO", "CODIGO"]),
        _metric("b_imagenes_tomadas", BRIEF, "Tablero Briefing", "IMAGENES TOMADAS", "IMAGENES_TOMADAS",
                pages=["Imagenes diagnosticas"]),
        _metric("l_peso", LAV, "Tablero Lavanderia", "PESO", "LAVANDERIA", pages=["Inicio"]),
        _metric("q_prog", QX, "Tablero Qx", "CIRUGIAS PROGRAMADAS", "QX", pages=["Cirugias"]),
        _metric("q_real", QX, "Tablero Qx", "CIRUGIAS REALIZADAS", "QX", pages=["Cirugias"]),
    ]
    files = {
        catalog / "source_registry.json": registry,
        rag / "visual_metrics_catalog.json": visuals_catalog,
        rag / "master_metrics.json": {"metrics": metrics},
        **{catalog / f"{key}_rag.json": value for key, value in technical.items()},
    }
    for path, data in files.items():
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class FakeProvider:
    """execute_dax para los VALUES(...) que usa el builder."""

    def __init__(self):
        self.queries = 0

    def execute_dax(self, dax, semantic_model=None):
        self.queries += 1
        compact = dax.replace("\n", "").replace(" ", "")
        for (model, table, column), values in DOMAINS.items():
            if model == semantic_model and f"VALUES('{table}'[{column}])" in compact:
                return {"status": "success", "rows": [{"[Value]": value} for value in values]}
        return {"status": "success", "rows": []}


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


def plan_for(question, **kwargs):
    return builder().build(question, **kwargs)


def option_ids(plan):
    resolution = plan.get("metric_resolution") or {}
    items = resolution.get("candidates") or resolution.get("suggestions") or []
    return [item["metric"]["metric_id"] for item in items]


def categorical(plan):
    return {
        (item["column"], str(item["value"]))
        for item in plan.get("filters", []) if item.get("type") == "categorical" and not item.get("temporal")
    }


# ---------------------------------------------------------------- palabras de petición (punto 2)
def test_request_words_tolerate_c_s_z_spelling():
    for word in ("necesito", "nesesito", "nesecito", "nezesito", "nesesitamos", "nesesitaria", "rekiero"):
        assert _is_request_word(canonical_token(word)), word
    for word in ("necropsia", "consulta", "sesion", "pediatria", "nefrologia"):
        assert not _is_request_word(canonical_token(word)), word


def test_typo_request_word_is_not_an_unresolved_filter():
    plan = plan_for("nesesito saber cuantos triages hay en el tablero briefing")
    assert plan["status"] == "ready", (plan["status"], plan.get("unresolved_text"))
    assert plan["metric"]["metric_id"] == "b_triages"
    assert not plan["unapplied_terms"], plan["unapplied_terms"]


# ---------------------------------------------------------------- nombres débiles (punto 1b)
def test_year_only_measure_is_never_chosen_by_the_year():
    plan = plan_for("cual fue el PIB de colombia en 2024")
    assert plan["status"] != "ready", plan.get("metric", {}).get("label")
    assert "a_2024" not in option_ids(plan), option_ids(plan)
    # Tampoco aparece entre las alternativas («Ninguna de las anteriores»).
    alternatives = builder().alternative_metrics("cuantas cirugias hubo en 2024")
    assert "a_2024" not in [item["metric"]["metric_id"] for item in alternatives]


def test_verb_alias_does_not_pick_a_metric():
    # «registrado» coincide con el alias técnico REGISTRADO de ASIGNADAS.
    plan = plan_for("cuantos pacientes hay registrados")
    assert plan.get("metric", {}).get("metric_id") != "b_asignadas", plan["status"]
    assert "b_asignadas" not in option_ids(plan)


def test_generic_only_name_is_not_chosen_with_certainty():
    plan = plan_for("cual es el promedio mensual")
    assert plan["status"] != "ready", plan.get("metric", {}).get("label")
    # ... pero dentro del tablero nombrado sí se puede elegir.
    named = plan_for("cual es el promedio mensual en el tablero atenciones")
    assert named["status"] == "ready" and named["metric"]["metric_id"] == "a_prom_mensual", named["status"]


# ---------------------------------------------------------------- tablero nombrado (punto 1c)
def test_named_board_without_the_metric_does_not_answer_with_another_board():
    plan = plan_for("cuantas imagenes tomadas hay en lavanderia")
    assert plan["status"] == "not_found", plan["status"]
    assert plan["reason"] == "metric_not_in_named_report", plan.get("reason")
    assert plan["named_report"] == "Tablero Lavanderia"
    # Lavandería no tiene un indicador parecido: se ofrece el del otro tablero como opción.
    assert option_ids(plan) == ["b_imagenes_tomadas"], option_ids(plan)
    assert any("Tablero Lavanderia" in note for note in plan.get("resolution_notes", []))


def test_named_board_with_similar_metrics_offers_them():
    plan = plan_for("cuanto peso de triages hay en el tablero lavanderia")
    if plan["status"] == "ready":
        assert plan["semantic_model"] == LAV, plan["semantic_model"]
    else:
        assert all(item["metric"]["semantic_model"] == LAV
                   for item in plan["metric_resolution"].get("suggestions") or []), option_ids(plan)


def test_dimension_word_is_not_a_named_board():
    # «eps» es una aseguradora aunque exista un tablero cuyo alias la contenga.
    b = builder()
    assert not b._board_named_explicitly(
        "que porcentaje de atenciones fueron de nueva eps",
        {"report": "TABLERO EPS", "semantic_model": "TABLERO EPS"},
    )
    assert b._board_named_explicitly("peso en lavanderia", {"report": "Tablero Lavanderia"})
    assert b._board_named_explicitly("triages del tablero de triage", {"report": "Otro"})


# ---------------------------------------------------------------- núcleo sin interpretar (punto 1a)
def test_head_noun_not_explained_is_not_offered_without_it():
    plan = plan_for("escribeme un codigo en python para ordenar una lista")
    assert plan["status"] == "not_found", plan["status"]
    assert plan["reason"] == "unresolved_words_outweigh_metric", plan.get("reason")
    assert plan["rejected_metric"]["metric_id"] == "b_productos"
    assert plan.get("unresolved_kind") == "out_of_scope", plan.get("unresolved_kind")


def test_unknown_qualifier_still_asks_without_it():
    # El sustantivo principal (triages) sí es el indicador: se pregunta «¿sin X?».
    plan = plan_for("cuantos triages zorbiformes hay en el tablero briefing")
    assert plan["status"] == "unsupported_filter", plan["status"]
    assert plan["reason"] == "possible_dimension_value_not_resolved"
    assert plan["unresolved_text"] == "zorbiformes"


# ---------------------------------------------------------------- calificativos (punto 3)
def test_stems_equate_plural_gender_and_derivation():
    assert _stem_token("pediatricos") == _stem_token("pediatria")
    assert _stem_token("ambulatorias") == _stem_token("ambulatorio")
    assert _stem_token("tomaron") == _stem_token("tomadas")
    assert _stem_token("sura") == "sura"  # nunca deja menos de 4 letras
    assert not _tokens_match_loosely("programada", "programacion")
    assert not _tokens_match_loosely("sura", "sur")


def test_qualifier_switches_to_the_metric_that_names_it():
    plan = plan_for("cuantos triages pediatricos hubo en 2025")
    assert plan["status"] == "ready", (plan["status"], option_ids(plan))
    assert plan["metric"]["metric_id"] == "a_triages_ped", plan["metric"]["metric_id"]
    assert "pediatricos" in (plan["metric_match"].get("interpretation") or "")
    # La medida ya es de 2025: el año pedido se aplica igual (no cambia el valor).
    assert any(item.get("year") == 2025 or item.get("value") == 2025 for item in plan["filters"]), plan["filters"]


def test_qualifier_in_the_metric_table_is_explained():
    plan = plan_for("cuantas consultas ambulatorias hay en el tablero atenciones")
    assert plan["status"] == "ready", (plan["status"], plan.get("unresolved_text"))
    assert plan["metric"]["metric_id"] == "a_consultas"
    assert not plan["unapplied_terms"], plan["unapplied_terms"]


def test_qualifiers_become_approximate_dimension_filters():
    plan = plan_for("cuantos triages pediatricos de sura hay en el tablero briefing")
    assert plan["status"] == "ready", (plan["status"], plan.get("unresolved_text"), plan.get("reason"))
    assert plan["metric"]["metric_id"] == "b_triages"
    assert categorical(plan) == {("SERVICIO", "PEDIATRIA"), ("ASEGURADORA", "SURA EPS")}, categorical(plan)
    assert not plan["unapplied_terms"], plan["unapplied_terms"]
    assert any("aproximada" in note for note in plan.get("resolution_notes", []))


def test_qualifier_never_matches_person_like_values():
    plan = plan_for("cuantos triages de pacientes zorbiformes hay en el tablero briefing")
    assert ("PACIENTE", "PACIENTE SIMULADO 00001") not in categorical(plan), categorical(plan)


def test_second_measure_is_not_taken_as_a_value():
    # «realizadas» nombra otro indicador del mismo modelo: no es ESTADO = Paciente Programado
    # ni cambia CIRUGIAS PROGRAMADAS por CIRUGIAS REALIZADAS.
    plan = plan_for("cirugias programadas y realizadas en el tablero qx")
    assert ("ESTADO", "Paciente Programado") not in categorical(plan), categorical(plan)
    assert plan.get("metric", {}).get("metric_id") != "q_real"


# ---------------------------------------------------------------- mismo nombre en varios tableros (punto 4)
def test_same_name_in_two_models_asks_with_year_variants_grouped():
    plan = plan_for("cuantos triages hubo en 2025")
    assert plan["status"] == "ambiguous", plan["status"]
    assert plan["reason"] == "same_name_in_several_boards", plan.get("reason")
    ids = option_ids(plan)
    assert ids[0] == "b_triages", ids
    # TRIAGES_2024/2025 y TOTAL_TRIAGES (sin visual, mismo modelo) son UNA opción: la base.
    assert ids[1:] == ["a_total_triages"], ids
    assert any("variantes por año" in note for note in plan.get("resolution_notes", []))


def test_named_board_breaks_the_same_name_tie():
    plan = plan_for("cuantos triages hubo en 2025 en el tablero briefing")
    assert plan["status"] == "ready" and plan["metric"]["metric_id"] == "b_triages", plan["status"]


def test_year_variants_without_base_keep_the_requested_year():
    b = builder()
    items = [{"metric": m} for m in b.metrics if m["metric_id"] in ("a_triages_2024", "a_triages_2025")]
    kept = b._collapse_year_variants(items, "triages en 2024")
    assert [item["metric"]["metric_id"] for item in kept] == ["a_triages_2024"]
    kept = b._collapse_year_variants(items, "triages")
    assert [item["metric"]["metric_id"] for item in kept] == ["a_triages_2025"]  # el más reciente


# ---------------------------------------------------------------- Runner mínimo
def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
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
