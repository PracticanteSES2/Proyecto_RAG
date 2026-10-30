"""
Indicador equivocado, ruta RAG para preguntas de datos, opciones mal rotuladas
y agrupación «y su respectiva X» (auditoría del banco real, corrida db2f1af),
offline con un catálogo mínimo:

  BRIEFING   EGRESOS PROBABLES (DISTINCTCOUNT) y EGRESOS EFECTIVOS HOY (SUM) en tarjetas;
             tabla «CAMAS OCUPADAS» que suma PACIENTE_ACOSTADO; CAMAS (COUNT, tarjeta)
  CITAS      %INASISTENCIA y CITAS CON ASISTENCIA; DEMANDA: CITAS (COUNT de otra tabla)
             y TOTAL_DEMANDA_INSATISFECHA (tablero «Demanda Insatisfecha»)
  URGENCIAS  TIEMPO PARA TRIAGE (AVERAGE de minutos), TRIAGES (conteo), TIEMPO EN
             URGENCIAS, TIEMPO PROMEDIO EN URGENCIAS PACIENTES HOSPITALIZADOS
  FACTURACION MONTO FACTURADO (SUM de FACTURADO)
  FARMACIA, ANTIBIOTICOS y LAVANDERIA para la ruta Power BI / RAG

Casos reales: BH08, AC03, DI01, FC05, TU03, TU13, BH03 (indicador); FM03, AB04,
LV02, LV03 (ruta); BH09 (descripción de opción); TU12 (agrupación).

Ejecutar:  python -m tests.resolution.test_indicador_ruta
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

from src.chatbot.option_describer import OptionDescriber  # noqa: E402
from src.semantic.query_plan_builder import (  # noqa: E402
    QueryPlanBuilder, _token_similarity, canonical_token,
)
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from src.semantic.table_titles import friendly_label, title_names_value  # noqa: E402
from tests.resolution.test_resolution import _source  # noqa: E402

BRIEF, CITAS, DEM, URG, FAC, FARM, ATB, LAV = (
    "BRIEFING", "ASIGNACION DE CITAS", "Demanda Insatisfecha", "TIEMPOS URGENCIAS",
    "CONTROL FACTURACION", "FARMACIA", "ANTIBIOTICOS", "LAVANDERIA",
)


def _metric(metric_id, model, label, table, expression, pages=("INICIO",), measure=None,
            visual_type="card", visual_title=None, aliases=(), aggregation=None, column=None):
    source_type = "explicit_measure" if measure else "visual_aggregation"
    return {
        "metric_id": metric_id, "label": label, "measure": measure,
        "aliases": [label, *aliases], "source_type": source_type,
        "semantic_model": model, "report": model, "reports": [model], "table": table,
        "dax_expression": f"[{measure}]" if measure else expression,
        "model_expression": expression if measure else None,
        "aggregation": aggregation, "column": column,
        "validation_status": "approved",
        "appearances": [
            {"report": model, "page_display_name": page, "visual_id": f"{metric_id}_{i}",
             "visual_title": visual_title, "visual_type": visual_type}
            for i, page in enumerate(pages)
        ],
    }


METRICS = [
    _metric("b_prob", BRIEF, "EGRESOS PROBABLES", "EGRESOS PROBABLES",
            "DISTINCTCOUNT('EGRESOS PROBABLES'[AINCONSEC])", pages=["EGRESOS PROBABLES"],
            aggregation="DistinctCount", column="AINCONSEC"),
    _metric("b_efect", BRIEF, "EGRESOS EFECTIVOS HOY", "EGRESOS PROBABLES",
            "SUM('EGRESOS PROBABLES'[EGRESO_EFECTIVO_HOY])", pages=["EGRESOS PROBABLES"],
            aggregation="Sum", column="EGRESO_EFECTIVO_HOY"),
    _metric("b_acostado", BRIEF, "CAMAS OCUPADAS", "GESTIÓN CAMAS", "SUM('GESTIÓN CAMAS'[PACIENTE_ACOSTADO])",
            pages=["GESTIÓN DE CAMAS"], visual_type="tableEx", visual_title="CAMAS OCUPADAS",
            aliases=["Suma de PACIENTE ACOSTADO"], aggregation="Sum", column="PACIENTE_ACOSTADO"),
    _metric("b_camas", BRIEF, "CAMAS", "CAMAS DISPONIBLES", "COUNT('CAMAS DISPONIBLES'[HCACODIGO])",
            pages=["GESTIÓN DE CAMAS"], aggregation="Count", column="HCACODIGO"),
    _metric("c_inasist", CITAS, "%INASISTENCIA", "CITAS_ASIGNADAS",
            "CALCULATE((sum(CITAS_ASIGNADAS[Inasistida])/sum(CITAS_ASIGNADAS[Asignada])))",
            pages=["OFERTA ESPECIALIDADES"], measure="%INASISTENCIA"),
    _metric("c_asist", CITAS, "CITAS CON ASISTENCIA", "CITAS_ASIGNADAS", "SUM('CITAS_ASIGNADAS'[CONFIRMADO])",
            pages=["COMPARATIVO ASIGNADAS"], aggregation="Sum", column="CONFIRMADO"),
    _metric("d_citas", DEM, "CITAS", "CITAS MEDICAS", "COUNT('CITAS MEDICAS'[OID])", pages=["CONSOLIDADO"],
            aggregation="Count", column="OID"),
    _metric("d_total", DEM, "TOTAL_DEMANDA_INSATISFECHA", "CALENDARIO", "[CIRUGIAS] + [CITAS]",
            pages=["CONSOLIDADO"], measure="TOTAL_DEMANDA_INSATISFECHA", aliases=["DEMANDA INSATISFECHA"]),
    _metric("u_triage", URG, "TIEMPO PARA TRIAGE", "OPORTUNIDAD_TRIAGE", "AVERAGE('OPORTUNIDAD_TRIAGE'[MIN])",
            pages=["RESUMEN"], aggregation="Average", column="MIN"),
    _metric("u_triages", URG, "TRIAGES", "TRIAGES", "DISTINCTCOUNT('TRIAGES'[OID_TRIAGE])", pages=["INICIO"],
            aggregation="DistinctCount", column="OID_TRIAGE"),
    _metric("u_urg", URG, "TIEMPO EN URGENCIAS", "TIEMPO_URGENCIAS",
            "AVERAGE('TIEMPO_URGENCIAS'[TiempoMinutosSalidaUrgencias])", pages=["TIEMPO ESTANCIA"],
            aggregation="Average", column="TiempoMinutosSalidaUrgencias"),
    _metric("u_hosp", URG, "TIEMPO PROMEDIO EN URGENCIAS PACIENTES HOSPITALIZADOS", "TIEMPO_HOSPI",
            "AVERAGE('TIEMPO_HOSPI'[TIEMPO_HOSPI])", pages=["TIEMPO ESTANCIA"],
            aggregation="Average", column="TIEMPO_HOSPI"),
    _metric("fac", FAC, "MONTO FACTURADO", "ULT_GESTION", "SUM('ULT_GESTION'[FACTURADO])",
            pages=["TRAZABILIDAD FACTURACION"], aggregation="Sum", column="FACTURADO",
            aliases=["Suma de FACTURADO", "FACTURADO"]),
    # AI03: el visual «GIRO CAMA» muestra GIRO_CAMA1; GIRO_CAMA (otra tabla) no está en ningún visual.
    _metric("giro1", URG, "GIRO_CAMA1", "FACT_EGRESOS", "DIVIDE([EGRESOS], [CAMAS])", pages=["INDICADORES"],
            measure="GIRO_CAMA1", visual_type="lineChart", visual_title="GIRO CAMA"),
    {**_metric("giro", URG, "GIRO_CAMA", "PROMEDIO_ESTANCIA", "DISTINCTCOUNT(PROMEDIO_ESTANCIA[adningreso])",
               measure="GIRO_CAMA"), "appearances": []},
    {**_metric("giro_otro", FAC, "GIRO_CAMA", "TABLA_GRD", "DISTINCTCOUNT(TABLA_GRD[adningreso])",
               measure="GIRO_CAMA"), "appearances": []},
    _metric("farm", FARM, "MEDICAMENTOS EN VENCIMIENTO 0-30 DÍAS", "VENCIMIENTO_PRODUCTOS",
            "DISTINCTCOUNT('VENCIMIENTO_PRODUCTOS'[IPRCODIGO])", pages=["MEDICAMENTOS VENCIDOS"],
            aggregation="DistinctCount", column="IPRCODIGO"),
    _metric("atb", ATB, "PAC_ACT", "ANTIBIOTICOS", "DISTINCTCOUNT(ANTIBIOTICOS[INGRESO])", pages=["ANTIBIOTICOS"],
            measure="PAC_ACT", aliases=["PACIENTES ACTIVOS"]),
    _metric("lav", LAV, "PESO TOTAL por Mes", "LAVANDERIA", "SUM('LAVANDERIA'[Peso])", pages=["Página 1"],
            aggregation="Sum", column="Peso"),
]

DICTIONARY = {
    "semantic_model": URG,
    "dashboards": [{
        "name": "DICCIONARIO TIEMPOS URGENCIAS", "is_dictionary": True,
        "documented_measures": [
            # Una medida del diccionario que el catálogo no tiene: no crea candidatos.
            {"table": "OPORTUNIDAD_TRIAGE", "name": "ESPERA_FANTASMA",
             "description": "Minutos de espera de la clasificación de pacientes. Tipo: decimal."},
        ],
        "other_sections": [
            {"section": "other", "heading": "Columnas clave",
             "text": "OPORTUNIDAD_TRIAGE[MIN]: Minutos de espera desde la llegada hasta la clasificación. "
                     "Tipo: entero. Se usa en: RESUMEN › Tarjeta."},
        ],
        "data_sources": ["OPORTUNIDAD_TRIAGE: Cada fila es una clasificación de pacientes en urgencias. "
                         "Origen: consulta SQL."],
    }],
}


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    keys = {BRIEF: "brief", CITAS: "citas", DEM: "dem", URG: "urg", FAC: "fac",
            FARM: "farm", ATB: "atb", LAV: "lav"}
    sources = [_source(key, model, model, [model.lower()]) for model, key in keys.items()]
    registry = {
        "models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                    "technical_catalog": s["technical_catalog"]} for s in sources],
        "sources": sources,
    }
    tables = {
        LAV: [("LAVANDERIA", ["Peso", "SERVICIO", "TURNO_OK", "Fecha"])],
        ATB: [("ANTIBIOTICOS", ["ANTIBIOTICO", "INGRESO"])],
    }
    files = {
        catalog / "source_registry.json": registry,
        rag / "visual_metrics_catalog.json": {"schema_version": 2, "reports": []},
        rag / "master_metrics.json": {"metrics": METRICS},
    }
    for model, key in keys.items():
        files[catalog / f"{key}_rag.json"] = {"semantic_model": model, "relationships": [], "tables": [
            {"name": name, "columns": [{"name": column, "data_type": "String"} for column in columns],
             "measures": []}
            for name, columns in tables.get(model, [])
        ]}
    folder = root / "data" / "semantic_documents" / "urg" / "md"
    folder.mkdir(parents=True)
    files[folder / "_diccionario.json"] = DICTIONARY
    for path, data in files.items():
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


def resolve(question):
    qpb = builder()
    return qpb._resolve_metric_flexible(question, qpb._source_context(question))


def plan_metric(question):
    plan = builder().build(question)
    # Sin columna de fecha en el catálogo mínimo el plan se detiene en el
    # periodo, pero el indicador ya está elegido.
    metric = plan.get("metric") or (plan.get("metric_resolution") or {}).get("metric") or {}
    return plan, metric.get("metric_id")


# ---------------------------------------------------------------- 1. palabras
def test_negated_word_is_not_the_same_word():
    assert _token_similarity("inasistencia", "asistencia") == 0.0
    assert _token_similarity("desocupada", "ocupada") == 0.0
    assert _token_similarity("insatisfecha", "satisfecha") == 0.0
    assert _token_similarity("asistencia", "asistencia") == 1.0


def test_conjugated_verb_matches_its_participle():
    assert _token_similarity("facturo", "facturado") >= 0.88
    assert _token_similarity("facturaron", "facturado") >= 0.88
    assert _token_similarity("cita", "citada") == 0.0  # raíz corta: no
    # «demoran», «tardan», «duran» preguntan por un tiempo.
    assert {canonical_token(word) for word in ("demoran", "tardan", "duran")} == {"tiempo"}


# ---------------------------------------------------------------- 2. indicador (BH08, AC03, DI01, FC05, TU03, TU13)
def test_today_does_not_switch_to_the_metric_named_today():
    plan, metric_id = plan_metric("cuantos egresos probables hay para hoy")
    assert metric_id == "b_prob", (plan.get("status"), metric_id, plan.get("resolution_notes"))


def test_percentage_in_words_names_the_percent_measure():
    plan, metric_id = plan_metric("cual es el porcentaje de inasistencia de las citas")
    assert metric_id == "c_inasist", (plan.get("status"), metric_id, plan.get("resolution_notes"))


def test_board_name_that_is_also_the_metric_name_is_kept():
    resolution = resolve("cual es la demanda insatisfecha total de este año")
    assert resolution.get("status") == "resolved", resolution.get("status")
    assert resolution["metric"]["metric_id"] == "d_total"


def test_conjugated_verb_resolves_the_amount_billed():
    resolution = resolve("cuanto se facturo el mes pasado")
    assert resolution.get("status") == "resolved", resolution.get("status")
    assert resolution["metric"]["metric_id"] == "fac"


def test_how_long_question_picks_the_time_not_the_count():
    resolution = resolve("cuanto se demoran en hacer el triage en promedio el mes pasado")
    assert resolution.get("status") == "resolved", [
        (item["metric"]["label"], item["score"]) for item in resolution.get("candidates") or []
    ]
    assert resolution["metric"]["metric_id"] == "u_triage"


def test_generic_unit_does_not_switch_to_a_narrower_metric():
    plan, metric_id = plan_metric("cuanto tiempo duran los pacientes en urgencias en promedio el mes pasado")
    assert metric_id == "u_urg", (plan.get("status"), metric_id, plan.get("resolution_notes"))


def test_visual_title_beats_hidden_homonym_measures():
    resolution = resolve("cual fue el giro cama del mes pasado")
    assert resolution.get("status") == "resolved", [
        (item["metric"]["label"], item["score"]) for item in resolution.get("candidates") or []
    ]
    assert resolution["metric"]["metric_id"] == "giro1"
    plan, metric_id = plan_metric("cual fue el giro cama del mes pasado")
    assert metric_id == "giro1" and plan.get("reason") != "same_name_in_several_boards", (
        plan.get("status"), plan.get("reason"), plan.get("resolution_notes"),
    )


# ---------------------------------------------------------------- 3. diccionario de variables
def test_dictionary_explains_words_without_creating_candidates():
    qpb = builder()
    triage = next(item for item in qpb.metrics if item["metric_id"] == "u_triage")
    tokens = qpb._dictionary_tokens(triage)
    assert {"minuto", "espera", "clasificacion"} <= tokens, tokens
    question = "minutos de espera del triage"
    explained = set()
    for value in [*qpb._metric_names(triage), triage.get("table")]:
        explained.update(canonical_tokens_of(value))
    assert qpb._dictionary_credit(question, explained, triage) > 0
    # La medida que solo existe en el diccionario nunca es candidata.
    resolution = resolve("espera fantasma")
    labels = [item["metric"]["label"] for item in resolution.get("candidates") or []]
    assert "ESPERA_FANTASMA" not in labels and resolution.get("status") != "resolved", (resolution.get("status"), labels)


def canonical_tokens_of(value):
    from src.semantic.query_plan_builder import canonical_tokens
    return canonical_tokens(value)


# ---------------------------------------------------------------- 4. títulos de tabla (BH03)
def test_table_title_is_not_the_name_of_the_summed_column():
    assert not title_names_value("tableEx", "CAMAS OCUPADAS", "Sum", "PACIENTE_ACOSTADO")
    assert title_names_value("tableEx", "CONSULTAS PRÓXIMA SEMANA", "Count", "CITA")
    assert title_names_value("card", "CAMAS OCUPADAS", "Sum", "PACIENTE_ACOSTADO")
    assert friendly_label("Sum", "PACIENTE_ACOSTADO", ["CAMAS OCUPADAS", "Suma de PACIENTE ACOSTADO"]) == (
        "Suma de PACIENTE ACOSTADO"
    )
    qpb = builder()
    relabeled = next(item for item in qpb.metrics if item["metric_id"] == "b_acostado")
    assert relabeled["label"] == "Suma de PACIENTE ACOSTADO", relabeled["label"]
    assert "CAMAS OCUPADAS" not in qpb._metric_names(relabeled)
    resolution = resolve("cuantas camas ocupadas tenemos")
    assert resolution.get("metric", {}).get("metric_id") != "b_acostado"
    assert all(item["metric"]["metric_id"] != "b_acostado" or item["score"] < 0.74
               for item in resolution.get("candidates") or [])


# ---------------------------------------------------------------- 5. ruta Power BI (FM03, AB04, LV02, LV03)
def test_informal_data_questions_go_to_power_bi():
    qpb = builder()
    for question in (
        "medicamentos que se vencen en los proximos 30 dias",
        "cual es el antibiotico que mas se esta usando?",
        "peso de ropa por servicio en lo que va del año",
        "en que turno se lava mas ropa?",
        "como va la ocupacion",
        "lista de pacientes en espera",
    ):
        assert qpb.looks_numeric(question), question


def test_documentation_questions_stay_in_rag():
    qpb = builder()
    for question in (
        "que significa porcentaje de inasistencia",
        "como se calcula el peso total por mes",
        "lista de indicadores del tablero de lavanderia",
        "dame la lista de los indicadores",
        "que es mas o menos el triage",
    ):
        assert not qpb.looks_numeric(question), question


# ---------------------------------------------------------------- 6. agrupación (TU12)
def test_respective_dimension_is_a_group_tail():
    qpb = builder()
    assert qpb._requested_group_tail(
        "cantidad de interconsultas solicitadas ayer y su respectiva especialidad"
    ) == "especialidad"
    assert qpb._requested_group_tail("citas con sus correspondientes servicios") == "servicios"
    assert qpb._requested_group_tail("ocupacion por servicio") == "servicio"


# ---------------------------------------------------------------- 7. descripción de opciones (BH09)
def test_option_description_respects_excluded_values():
    expression = (
        "CALCULATE(DISTINCTCOUNT('PACIENTES HOSPITALIZADOS'[PACNUMDOC]), KEEPFILTERS(FILTER("
        "ALL('PACIENTES HOSPITALIZADOS'[GASNOMBRE]), NOT ('PACIENTES HOSPITALIZADOS'[GASNOMBRE] IN "
        "{\"UNIDAD OBSTETRICIA\"}))))"
    )
    option = {"id": "1", "label": "PACIENTES HOSPITALIZADOS", "dax_expression": expression}
    describer = OptionDescriber(None)
    assert describer.filter_conditions(expression) == [("GASNOMBRE", "excluye", ["UNIDAD OBSTETRICIA"])]
    assert "EXCLUYE GASNOMBRE = UNIDAD OBSTETRICIA" in describer.build_prompt(option)
    assert describer.contradicts_filters("Cuenta los pacientes hospitalizados en la unidad obstétrica.", option)
    assert not describer.contradicts_filters("Cuenta los pacientes hospitalizados sin la unidad obstétrica.", option)
    occupied = "CALCULATE(COUNT('CAMAS'[HCACODIGO]), 'CAMAS'[ESTADOS_CAM] IN {\"OCUPADA\"})"
    assert describer.filter_conditions(occupied) == [("ESTADOS_CAM", "solo", ["OCUPADA"])]


def test_describe_rejects_a_contradicting_llm_description():
    class FakeLLM:
        def chat(self, *args, **kwargs):
            return "Cuenta los pacientes de la unidad obstétrica."

    describer = OptionDescriber(FakeLLM())
    describer._describe_one = lambda option: {"status": "success", "answer": "Cuenta los pacientes de la unidad obstétrica."}
    option = {"id": "1", "label": "PACIENTES HOSPITALIZADOS",
              "dax_expression": "CALCULATE(DISTINCTCOUNT('P'[DOC]), NOT ('P'[GASNOMBRE] IN {\"UNIDAD OBSTETRICIA\"}))"}
    result = describer.describe("pregunta", [option])
    assert "1" not in result["descriptions"] and result["rejected"].get("1") == ["filtro excluido"], result


TESTS = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]


def main():
    failed = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} pruebas OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
