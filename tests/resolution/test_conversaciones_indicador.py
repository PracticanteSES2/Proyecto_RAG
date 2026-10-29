"""
Conversaciones reales del 2026-10-29 (Power BI real, sin LLM) reducidas a un
catálogo mínimo offline con la forma de la metadata real (INFO.VIEW):

  BRIEF  %OCUPACION (CAMAS DISPONIBLES, página INICIO); CANTIDAD DE PACIENTES
         (PACIENTES X ASEGURADORA, con ESPECIALIDAD y HSUNOMBRE); TOTAL DE
         PACIENTES (PACIENTES EMERGENCIA, sin especialidad, con un filtro del
         visual sobre INTERCONSULTAS, tabla SIN relación con ella);
         INTERCONSULTAS SIN RESPUESTA (INTERCONSULTAS, con GEEDESCRI).
  GEST   %OCUPACION de «Dashboard Gestion» (modelo sin informe).
  TURG   página INTERCONSULTAS: %ATENDIDO, INTERCONSULTAS SOLICITADAS /
         RESPONDIDAS (INTERCONSULTA, con GEEDESCRI) y RESPUESTAS ... 24 HORAS
         (suma de un tiempo, INTERCONSULTA_DIA).
  NAOS   PACIENTES (PACIENTES, sin especialidad).
  ATEN/QX  CAMAS OCUPADAS en dos tableros con informe (la ambigüedad sigue).

1. Homónimos: solo uno en un informe -> se usa ese (sin contrapregunta).
2. «nivel/índice/grado de» es forma de indicador, no «No pude aplicar».
3. «cada una / su respectiva X» = agrupar por la dimensión, nunca un valor.
4. «que tantas ... se están manejando»: interrogativo y verbo, no filtros.
5. Un filtro de visual sobre una tabla sin relación no conecta dimensiones.
6. Página nombrada por su tema: «cantidad de» y «por X» depuran opciones.

Ejecutar:  python -m tests.resolution.test_conversaciones_indicador
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

from src.semantic.query_plan_builder import QueryPlanBuilder, canonical_phrases  # noqa: E402
from src.semantic.request_phrases import rewrite_request  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from tests.resolution.test_resolution import _source  # noqa: E402

BRIEF, GEST, TURG, NAOS, ATEN, QX = (
    "BRIEFING HOSPITALARIO", "Dashboard Gestion", "TABLERO TIEMPOS URGENCIAS", "TABLERO NAOS",
    "TABLERO ATENCIONES", "TABLERO QX",
)


def _metric(metric_id, model, label, table, expression, page=None, visual_type="card",
            source_type="visual_aggregation", **extra):
    explicit = source_type == "explicit_measure"
    return {
        "metric_id": metric_id, "label": label, "measure": label if explicit else None,
        "aliases": [label], "source_type": source_type, "semantic_model": model,
        "report": model if page else None, "reports": [model] if page else [], "table": table,
        "dax_expression": f"[{label}]" if explicit else expression,
        "model_expression": expression if explicit else None, "validation_status": "approved",
        "appearances": [{"report": model, "page_display_name": page, "visual_id": f"{metric_id}_v",
                         "visual_title": None, "visual_type": visual_type}] if page else [],
        **extra,
    }


_TOTAL_BASE = "DISTINCTCOUNT('PACIENTES EMERGENCIA'[DOCUMENTO])"
METRICS = [
    _metric("b_ocup", BRIEF, "%OCUPACION", "CAMAS DISPONIBLES",
            "DIVIDE(COUNT('CAMAS DISPONIBLES'[OCUPADA]), COUNT('CAMAS DISPONIBLES'[HCACODIGO]))",
            page="INICIO", source_type="explicit_measure"),
    _metric("g_ocup", GEST, "%OCUPACION", "DIM_CAMAS_DIR",
            "SUM(DIM_CAMAS_DIR[OCUPADAS])/COUNT(DIM_CAMAS_DIR[HCACODIGO])", source_type="explicit_measure"),
    _metric("b_cant", BRIEF, "CANTIDAD DE PACIENTES", "PACIENTES X ASEGURADORA",
            "DISTINCTCOUNT('PACIENTES X ASEGURADORA'[ADNINGRESO])", page="DETALLE OCUPACIÓN"),
    _metric("b_total", BRIEF, "TOTAL DE PACIENTES", "PACIENTES EMERGENCIA",
            "CALCULATE(" + _TOTAL_BASE + ", KEEPFILTERS(FILTER(ALL('INTERCONSULTAS'[OID_RESPUESTA]), "
            "ISBLANK('INTERCONSULTAS'[OID_RESPUESTA]))))", page="INICIO",
            base_dax_expression=_TOTAL_BASE,
            visual_filters=[{"table": "INTERCONSULTAS", "column": "OID_RESPUESTA", "condition": {},
                             "text": "OID_RESPUESTA en blanco"}]),
    _metric("b_ic_sin", BRIEF, "INTERCONSULTAS SIN RESPUESTA", "INTERCONSULTAS",
            "DISTINCTCOUNT('INTERCONSULTAS'[OID_SOLICITUD])", page="INTERCONSULTAS"),
    _metric("n_pac", NAOS, "PACIENTES", "PACIENTES", "DISTINCTCOUNT('PACIENTES'[AINCONSEC])", page="LISTADO"),
    _metric("t_pct", TURG, "%ATENDIDO", "INTERCONSULTA",
            "SUM(INTERCONSULTA[RESPUESTAS])/SUM(INTERCONSULTA[SOLICITUDES])", page="INTERCONSULTAS",
            source_type="explicit_measure"),
    _metric("t_sol", TURG, "INTERCONSULTAS SOLICITADAS", "INTERCONSULTA",
            "SUM('INTERCONSULTA'[SOLICITUDES])", page="INTERCONSULTAS"),
    _metric("t_resp", TURG, "INTERCONSULTAS RESPONDIDAS", "INTERCONSULTA",
            "SUM('INTERCONSULTA'[RESPUESTAS])", page="INTERCONSULTAS"),
    _metric("t_24h", TURG, "RESPUESTAS A INTERCONSULTA ÚLTIMAS 24 HORAS", "INTERCONSULTA_DIA",
            "SUM('INTERCONSULTA_DIA'[TIEMPO_RESPUESTA_INTERCONSULTA])", page="INTERCONSULTAS",
            visual_type="tableEx"),
    _metric("a_camas", ATEN, "CAMAS OCUPADAS", "CAMAS", "COUNT('CAMAS'[ID])", page="CAMAS"),
    _metric("q_camas", QX, "CAMAS OCUPADAS", "CAMAS", "COUNT('CAMAS'[ID])", page="QUIROFANOS"),
]

TABLES = {
    BRIEF: [("CAMAS DISPONIBLES", ["HCACODIGO", "OCUPADA"]),
            ("PACIENTES X ASEGURADORA", ["ADNINGRESO", "ESPECIALIDAD", "HSUNOMBRE", "GPANOMCOM"]),
            ("PACIENTES EMERGENCIA", ["DOCUMENTO", "ASEGURADOR", "CLASIFICACIÓN"]),
            ("INTERCONSULTAS", ["OID_SOLICITUD", "OID_RESPUESTA", "GEEDESCRI", "HSUNOMBRE"])],
    GEST: [("DIM_CAMAS_DIR", ["HCACODIGO", "OCUPADAS"])],
    TURG: [("INTERCONSULTA", ["OID_SOLICITUD", "SOLICITUDES", "RESPUESTAS", "GEEDESCRI", "FECHA_SOLICITUD"]),
           ("INTERCONSULTA_DIA", ["OID_SOLICITUD", "TIEMPO_RESPUESTA_INTERCONSULTA"])],
    NAOS: [("PACIENTES", ["AINCONSEC", "HSUNOMBRE"])],
    ATEN: [("CAMAS", ["ID", "SERVICIO"])],
    QX: [("CAMAS", ["ID", "SALA"])],
}
# Relaciones reales: PACIENTES EMERGENCIA solo se relaciona con el calendario.
RELATIONSHIPS = {BRIEF: [{"FromTable": "AUDITORIA", "FromColumn": "INGRESO", "ToTable": "PACIENTES X ASEGURADORA",
                          "ToColumn": "ADNINGRESO", "IsActive": True}]}
DOMAINS = {
    (BRIEF, "PACIENTES X ASEGURADORA", "HSUNOMBRE"): ["URGENCIAS", "HOSPITALIZACION"],
    (BRIEF, "PACIENTES X ASEGURADORA", "ESPECIALIDAD"): ["MEDICINA DE URGENCIAS", "PEDIATRIA"],
    (BRIEF, "INTERCONSULTAS", "HSUNOMBRE"): ["URGENCIAS", "HOSPITALIZACION"],
}
ALIASES = {"ESPECIALIDAD": "ESPECIALIDAD", "GEEDESCRI": "ESPECIALIDAD", "HSUNOMBRE": "SERVICIO"}


def _field(table, column):
    return {"role": "Values", "kind": "column", "table": table, "column": column,
            "display_name": ALIASES.get(column, column), "native_query_ref": column,
            "query_ref": f"{table}.{column}"}


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    keys = {BRIEF: "brief", GEST: "gest", TURG: "turg", NAOS: "naos", ATEN: "aten", QX: "qx"}
    sources = [_source(key, model, model, [model.lower()]) for model, key in keys.items()]
    registry = {
        "models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                    "technical_catalog": s["technical_catalog"]} for s in sources],
        "sources": sources,
    }
    technical = {
        key: {"semantic_model": model, "relationships": RELATIONSHIPS.get(model, []), "tables": [
            {"name": name, "columns": [{"name": column, "data_type": "DateTime" if column.startswith("FECHA") else "String"}
                         for column in columns],
             "measures": [{"name": m["label"], "expression": m["model_expression"]}
                          for m in METRICS if m["semantic_model"] == model and m["table"] == name
                          and m["model_expression"]]}
            for name, columns in TABLES[model]
        ]}
        for model, key in keys.items()
    }

    def page(model, name, visuals):
        return {"report": model, "semantic_model": model, "source_group": keys[model], "pages": [
            {"page_name": name, "page_display_name": name, "filters": {}, "visuals": visuals}]}

    visuals = {"schema_version": 2, "reports": [
        page(BRIEF, "DETALLE OCUPACIÓN", [
            {"visual_id": "b_cant_v", "visual_type": "card", "fields": []},
            {"visual_id": "b_tabla", "visual_type": "tableEx", "fields": [
                _field("PACIENTES X ASEGURADORA", "ESPECIALIDAD"), _field("PACIENTES X ASEGURADORA", "HSUNOMBRE")]},
        ]),
        page(BRIEF, "INTERCONSULTAS", [{"visual_id": "b_ic_sin_v", "visual_type": "card", "fields": []}]),
        page(TURG, "INTERCONSULTAS", [
            {"visual_id": f"{m}_v", "visual_type": "card", "fields": []} for m in ("t_pct", "t_sol", "t_resp")
        ] + [{"visual_id": "t_esp", "visual_type": "slicer", "fields": [_field("INTERCONSULTA", "GEEDESCRI")]}]),
    ]}
    files = {
        catalog / "source_registry.json": registry,
        rag / "visual_metrics_catalog.json": visuals,
        rag / "master_metrics.json": {"metrics": METRICS},
        **{catalog / f"{key}_rag.json": value for key, value in technical.items()},
    }
    for path, data in files.items():
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class FakeProvider:
    def execute_dax(self, dax, semantic_model=None):
        compact = dax.replace("\n", "").replace(" ", "")
        for (model, table, column), values in DOMAINS.items():
            if model == semantic_model and f"VALUES('{table}'[{column}])".replace(" ", "") in compact:
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


def _metric_by_id(metric_id):
    return next(m for m in builder().metrics if m["metric_id"] == metric_id)


def _candidate_ids(plan):
    return [c["metric"]["metric_id"] for c in (plan.get("metric_resolution") or {}).get("candidates") or []]


def _notes(plan):
    return " | ".join(plan.get("resolution_notes") or [])


# ---------------------------------------------------------------- 1. homónimos con y sin informe
def test_homonym_without_report_is_not_offered():
    plan = builder().build("cual es el nivel de ocupacion?")
    assert plan["status"] == "ready", (plan["status"], _candidate_ids(plan), _notes(plan))
    assert plan["metric"]["metric_id"] == "b_ocup", plan["metric"]["metric_id"]
    assert "está en un informe" in _notes(plan), _notes(plan)
    assert not plan.get("unapplied_terms"), plan.get("unapplied_terms")


def test_homonyms_with_report_still_ask():
    plan = builder().build("cuantas camas ocupadas hay")
    assert plan["status"] == "ambiguous", (plan["status"], _notes(plan))
    assert set(_candidate_ids(plan)) == {"a_camas", "q_camas"}, _candidate_ids(plan)


# ---------------------------------------------------------------- 2. forma del indicador
def test_indicator_form_words_are_not_filters():
    qpb = builder()
    # Elegida a mano (botón) la medida sin informe: «nivel» tampoco queda sin aplicar.
    plan = qpb.build("cual es el nivel de ocupacion?", selected_metric_id="g_ocup")
    assert plan["status"] == "ready" and not plan.get("unapplied_terms"), plan.get("unapplied_terms")
    for question in ("indice de ocupacion", "grado de ocupacion", "porcentaje de ocupacion"):
        plan = qpb.build(question, selected_metric_id="b_ocup")
        assert plan["status"] == "ready" and not plan.get("unapplied_terms"), (question, plan.get("unapplied_terms"))
    # «nivel 3» (sin «de») sí puede ser un valor: no se consume.
    assert "nivel" not in qpb._measure_type_words("pacientes nivel 3", _metric_by_id("b_cant"))


# ---------------------------------------------------------------- 3. «cada una» / «su respectiva»
def test_anaphoric_each_groups_by_previous_dimension():
    recognizer = builder().grouping_dimension_name
    text, notes = rewrite_request(
        "necsito saber que tantas especialidades se estan manejando en el area e urgencias "
        "y a cantidad de paciente que tiene cada una", dimension=recognizer,
    )
    assert text.endswith("por especialidad"), text
    assert "cada una" not in text and notes, (text, notes)
    text, _ = rewrite_request("cuantos servicios hay y cuantos egresos tuvo cada uno", dimension=recognizer)
    assert text.endswith("por servicio"), text
    # Sin antecedente que sea una dimensión (o de otro género) no se inventa.
    text, notes = rewrite_request("cuantos pacientes y la estancia de cada uno", dimension=recognizer)
    assert not notes, (text, notes)


def test_respective_dimension_groups():
    recognizer = builder().grouping_dimension_name
    for question in ("identifica la cantidad de interconsultas del día de ayer y su respectiva especialidad",
                     "interconsultas de ayer con sus respectivas especialidades",
                     "interconsultas y su especialidad"):
        text, notes = rewrite_request(question, dimension=recognizer)
        assert text.endswith("por especialidad") and notes, (question, text)
        assert "respectiv" not in text, text


# ---------------------------------------------------------------- 4. tipeo y verbos
def test_colloquial_question_words_are_not_filters():
    text, changes = canonical_phrases("que tantas especialidades se estan manejando en urgencias")
    assert "manejando" not in text and changes, (text, changes)
    assert canonical_phrases("pacientes del dr fernando")[1] == []  # gerundio sin auxiliar: no se toca


def test_patients_per_specialty_in_emergency_area():
    question = ("necsito saber que tantas especialidades se estan manejando en el area e urgencias "
                "y a cantidad de paciente por especialidad")
    plan = builder().build(question)
    assert plan["status"] == "ready", (plan["status"], plan.get("reason"), _candidate_ids(plan), _notes(plan))
    assert plan["metric"]["metric_id"] == "b_cant", plan["metric"]["metric_id"]
    assert [g["column"] for g in plan["group_by"]] == ["ESPECIALIDAD"], plan["group_by"]
    filters = {(f.get("column"), f.get("value")) for f in plan["filters"]}
    assert ("HSUNOMBRE", "URGENCIAS") in filters, plan["filters"]
    assert not plan.get("unapplied_terms"), plan.get("unapplied_terms")


# ---------------------------------------------------------------- 5. filtro de visual sin relación
def test_visual_filter_table_without_relationship_is_unrelated():
    qpb = builder()
    total = _metric_by_id("b_total")
    field = {"table": "INTERCONSULTAS", "column": "GEEDESCRI", "aliases": ["ESPECIALIDAD"]}
    assert qpb._dimension_relation(total, field) == "unrelated"
    own = {"table": "PACIENTES EMERGENCIA", "column": "ASEGURADOR"}
    assert qpb._dimension_relation(total, own) == "own"


# ---------------------------------------------------------------- 6. página nombrada por su tema
def test_count_and_group_narrow_page_options():
    plan = builder().build("identifica la cantidad de interconsultas del dia de ayer por especialidad")
    ids = _candidate_ids(plan) if plan["status"] == "ambiguous" else [plan["metric"]["metric_id"]]
    # Ni el porcentaje ni la suma de tiempos responden «cantidad de»; las que
    # quedan se desglosan por especialidad.
    assert "t_pct" not in ids and "t_24h" not in ids, (ids, _notes(plan))
    assert {"t_sol", "t_resp"} <= set(ids) or plan["status"] == "ready", (ids, _notes(plan))
    qpb = builder()
    narrowed = qpb._narrow_page_options(
        "cantidad de interconsultas por especialidad",
        [{"metric": _metric_by_id(i), "score": 1.0, "business_score": 1.0} for i in ("t_pct", "t_sol", "t_24h")],
    )
    assert [i["metric"]["metric_id"] for i in narrowed] == ["t_sol"], narrowed


def test_chosen_interconsultation_groups_by_specialty():
    qpb = builder()
    # (el periodo «ayer» y su columna de fecha los resuelve otro módulo; aquí
    # solo se comprueba que «del día de» es parte del periodo, no un filtro)
    assert "dia" in qpb._analyze_periods("cantidad de interconsultas del dia de ayer")["tokens"]
    plan = qpb.build("identifica la cantidad de interconsultas por especialidad", selected_metric_id="t_sol")
    assert plan["status"] == "ready", (plan["status"], plan.get("reason"))
    assert [g["column"] for g in plan["group_by"]] == ["GEEDESCRI"], plan["group_by"]
    assert not plan.get("unapplied_terms"), plan.get("unapplied_terms")


def main():
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"OK    {name}")
        except Exception:
            failed += 1
            print(f"FALLA {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} pruebas OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
