"""
Ronda r5 (holdout v1, 40 % auditado): reglas GENERALES de resolución, cada una
validada con preguntas NUEVAS (no del holdout ni del banco de desarrollo) sobre
un catálogo mínimo offline (tablero ficticio de «Tablero Gestión» y
«Tablero Ropa»).

  1. Contrapregunta innecesaria: verbos («llegaron», «suben», «pasan»),
     participios de la acción del tablero («lavados» en LAVANDERÍA) y palabras
     del nombre funcional documentado de la página («pendientes» en una página
     de «pacientes con pendientes activos») no son filtros; variantes de una
     misma medida (PROM_X, X_ANUAL, X2025, medida que envuelve [X]) son una
     opción; una opción que explica solo parte de lo que explica otra no se
     ofrece.
  2. Indicador: raíz común de la documentación («lavado» ~ «lavandería»).
  3. Datos ↔ RAG: frase nominal que empieza por una página con datos y sigue
     con su tablero; «por qué etapas pasa / qué pasos tiene» es descriptiva.
  4. Agrupación: «por <X>» también por la descripción documentada de la
     columna («rango de horas», «causa» ~ «motivo»), sin el interrogativo.
  5. Cobertura: tablas de «próximos días» no responden un periodo pasado;
     «Origen: consulta SQL sobre T» hereda la ventana de T; «hoy» sobre el
     corte del día anterior responde el corte.
  6. Filtro: una palabra común a varios valores (en cualquier posición)
     filtra por todos ellos.

Ejecutar:  python -m tests.resolution.test_r5
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
from src.semantic.question_kind import descriptive_phrase  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from src.semantic.table_coverage import coverage_window, covers  # noqa: E402
from tests.resolution.test_resolution import _source  # noqa: E402

GES = "Tablero Gestion"
ROPA = "Tablero Ropa"
TODAY = date(2026, 10, 30)
LAST_MONTH = (date(2026, 9, 1), date(2026, 10, 1))


def _metric(metric_id, label, model, table, dax, pages, aggregation="DistinctCount", measure=None):
    return {
        "metric_id": metric_id, "label": label, "measure": measure, "aliases": [label],
        "source_type": "visual_aggregation", "semantic_model": model, "report": model, "reports": [model],
        "table": table, "column": "X", "aggregation": aggregation, "dax_expression": dax,
        "validation_status": "approved",
        "appearances": [{"report": model, "page_display_name": page, "page_name": page,
                         "visual_id": f"v_{metric_id}_{index}", "visual_title": None, "visual_type": "card"}
                        for index, page in enumerate(pages)],
    }


METRICS = [
    _metric("pacientes", "PACIENTES", GES, "PACIENTES_G", "DISTINCTCOUNT('PACIENTES_G'[DOC])", ["LISTADO"]),
    _metric("visitas", "VISITAS", GES, "VISITAS", "DISTINCTCOUNT('VISITAS'[OID])", ["VISITAS"]),
    _metric("visitas_dom", "VISITAS DOMICILIARIAS", GES, "VISITAS_DOM", "DISTINCTCOUNT('VISITAS_DOM'[OID])",
            ["DOMICILIARIAS"]),
    _metric("anuladas", "VISITAS ANULADAS", GES, "VISITAS", "CALCULATE(DISTINCTCOUNT('VISITAS'[OID]))", ["ANULADAS"]),
    _metric("prog", "PROGRAMADAS", GES, "PROGRAMADAS", "COUNT('PROGRAMADAS'[CITA])", ["PROXIMAS"], "Count"),
    _metric("peso", "PESO", ROPA, "LAVANDERIA", "SUM('LAVANDERIA'[PESO])", ["Página 1"], "Sum"),
]

DICTIONARIES = {
    "ges": {"semantic_model": GES, "dashboards": [{
        "name": "DICCIONARIO GESTION", "is_dictionary": True,
        "data_sources": [
            "PROGRAMADAS: Citas usadas por la matriz. Origen: consulta SQL sobre BI_AGENDA en la base X (Import). "
            "Granularidad: una fila por cita.",
            "BI_AGENDA: Citas asignadas para los próximos días con tipo y fecha.",
            "VISITAS: Visitas del día anterior con clase y fecha. Origen: SQL.",
        ],
        "other_sections": [
            {"text": "VISITAS[RANGO_ESPERA]: Rango de horas de espera de la visita. Tipo: texto. "
                     "Valores: 1. 0-6 horas, 2. 6-12 horas."},
            {"text": "VISITAS[MOTIVO_COD]: Causa de anulación de la visita. Tipo: texto."},
            {"text": "VISITAS[SERVICIO]: Servicio que atiende la visita. Tipo: texto."},
        ],
    }]},
}


def _page_doc(model, page, functional, block="Día"):
    return {"semantic_model": model, "dashboards": [{
        "name": page, "md_metadata": {"tablero": model, "pagina": page, "bloque": block,
                                      "nombre_funcional": functional}}]}


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    sources = [_source("ges", GES, GES, ["tablero gestion"]), _source("ropa", ROPA, ROPA, ["lavanderia"])]
    docs = root / "data" / "semantic_documents"
    files = {
        catalog / "source_registry.json": {
            "models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                        "technical_catalog": s["technical_catalog"]} for s in sources],
            "sources": sources},
        rag / "visual_metrics_catalog.json": {"schema_version": 2, "reports": []},
        rag / "master_metrics.json": {"metrics": METRICS},
        catalog / "ges_rag.json": {"semantic_model": GES, "relationships": [], "tables": []},
        catalog / "ropa_rag.json": {"semantic_model": ROPA, "relationships": [], "tables": []},
        docs / "ges" / "md" / "_diccionario.json": DICTIONARIES["ges"],
        docs / "ges" / "md" / "_general.json": _page_doc(GES, "GENERAL", "Seguimiento de gestiones", "General"),
        docs / "ges" / "md" / "listado.json": _page_doc(GES, "LISTADO", "Listado de pacientes con pendientes activos"),
        docs / "ges" / "md" / "anuladas.json": _page_doc(GES, "ANULADAS", "Visitas anuladas por causas institucionales"),
        docs / "ropa" / "md" / "p1.json": _page_doc(ROPA, "Página 1", "Peso de ropa recibida en lavandería"),
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
            router, FakeProvider(), project_root=root, today=TODAY,
        )
    return _STATE["builder"]


def engine():
    """QueryEngine mínimo: solo lo que usan las reglas de opciones."""
    instance = QueryEngine.__new__(QueryEngine)
    instance.query_plan_builder = builder()
    instance._trace = None
    return instance


def _by_id(metric_id):
    return next(metric for metric in METRICS if metric["metric_id"] == metric_id)


def _field(table, column, aliases):
    return {"semantic_model": GES, "table": table, "column": column, "aliases": aliases,
            "kind": "column", "relevance_score": 10}


# ------------------------------------------------------------ 1. palabras implícitas
def test_verbs_are_not_filters():
    # Nuevas: «cuántos pedidos LLEGARON», «hasta que lo SUBEN», «cuánto PASAN».
    implied, remaining = builder().implied_words(_by_id("visitas"), "llegaron suben pasan")
    assert not remaining, remaining
    assert set(implied) == {"llegaron", "suben", "pasan"}, implied


def test_functional_page_name_words_are_not_filters():
    # Nueva: «cuántos pacientes tienen pendientes activos» en LISTADO.
    implied, remaining = builder().implied_words(_by_id("pacientes"), ["pendientes", "activos"])
    assert not remaining, remaining


def test_participle_of_the_board_action_is_not_a_filter():
    # Nueva: «kilos de ropa LAVADOS en agosto» con el tablero de lavandería.
    implied, remaining = builder().implied_words(_by_id("peso"), ["lavados"])
    assert implied == ["lavados"] and not remaining, (implied, remaining)


def test_verb_form_explained_by_another_page_of_the_same_table():
    # Nueva: «por qué causas ANULÓ visitas la institución» con VISITAS: la
    # página ANULADAS de la misma tabla («visitas anuladas por causas
    # institucionales») explica la forma verbal; un sustantivo con indicador
    # propio («domiciliarias») no.
    implied, remaining = builder().implied_words(_by_id("visitas"), ["anulo", "domiciliarias"])
    assert implied == ["anulo"] and remaining == ["domiciliarias"], (implied, remaining)


def test_board_documentation_names_the_only_weight_measure():
    # Nueva: «cuánta ropa RECIBIÓ la lavandería el mes pasado» -> PESO
    # («Peso de ropa recibida en lavandería»).
    qpb = builder()
    question = "cuanta ropa recibio la lavanderia el mes pasado"
    resolution = qpb._resolve_metric_flexible(question, qpb._source_context(question))
    assert (resolution.get("metric") or {}).get("metric_id") == "peso", (
        resolution.get("status"), (resolution.get("metric") or {}).get("label"))


def test_real_filter_words_are_still_unresolved():
    # Una palabra que no dice el indicador ni es verbo sigue pidiendo aclaración.
    implied, remaining = builder().implied_words(_by_id("visitas"), ["ortopedia", "baja"])
    assert remaining == ["ortopedia", "baja"], (implied, remaining)


def test_metric_covered_by_page_and_verb_answers_without_confirming():
    # Nueva: «cuántos pacientes hay registrados en el listado» -> PACIENTES (LISTADO).
    assert builder().metric_covers_question("cuantos pacientes hay registrados en el listado", _by_id("pacientes"))
    assert not builder().metric_covers_question("cuantos pacientes de ortopedia", _by_id("visitas"))


# ------------------------------------------------------------ 1. variantes y opciones dominadas
def _option(metric_id, label, dax, model=GES, measure=None):
    return {"metric_id": metric_id, "label": label, "measure": measure or label, "semantic_model": model,
            "dax_expression": dax, "table": "VISITAS_DOM", "appearances": []}


def test_variants_of_one_measure_collapse_to_the_base():
    # Nueva: «cuántas visitas domiciliarias hubo en 2024» con VISITA_DOM, PROM_VISITA_DOM,
    # VISITA_DOM_ANUAL y PROYECCION_VISDOM: se ofrece la base.
    scored = [(1.0, _option(i, label, "[X]")) for i, label in enumerate(
        ["PROM_VISITA_DOM", "VISITA_DOM", "VISITA_DOM_ANUAL", "PROYECCION_VISDOM", "VISDOM2024"])]
    kept = engine()._collapse_measure_variants("cuantas visitas domiciliarias hubo en 2024", scored)
    labels = [metric["label"] for _, metric in kept]
    assert labels == ["VISDOM2024"] or labels == ["VISITA_DOM"], labels


def test_named_variant_is_kept():
    # Nueva: «promedio de visitas domiciliarias»: la variante pedida se queda.
    scored = [(1.0, _option(i, label, "[X]")) for i, label in enumerate(["PROM_VISITA_DOM", "VISITA_DOM"])]
    kept = engine()._collapse_measure_variants("promedio mensual de visitas domiciliarias", scored)
    assert [metric["label"] for _, metric in kept] == ["PROM_VISITA_DOM"], kept


def test_different_measures_are_not_variants():
    scored = [(1.0, _option(1, "VISITAS ATENDIDAS", "[X]")), (1.0, _option(2, "VISITAS CANCELADAS", "[Y]"))]
    assert len(engine()._collapse_measure_variants("visitas", scored)) == 2


def test_range_in_the_question_picks_the_bracket_that_contains_it():
    # Nuevas: «insumos que vencen entre 1 y 3 semanas» (7-21 días) -> 0-30 DÍAS;
    # «entre 2 y 6 meses» (60-180) no cabe en ningún tramo: se pregunta.
    def scored():
        return [(1.0, _option(1, "INSUMOS EN VENCIMIENTO 0-30 DÍAS", "[A]")),
                (1.0, _option(2, "INSUMOS EN VENCIMIENTO 30-120 DÍAS", "[B]")),
                (1.0, _option(3, "CANTIDAD", "[C]"))]
    kept = engine()._options_matching_range("cuantos insumos vencen entre 1 y 3 semanas", scored())
    assert [metric["metric_id"] for _, metric in kept] == [1], kept
    kept = engine()._options_matching_range("cuantos insumos se vencen entre 2 y 4 meses", scored())
    assert [metric["metric_id"] for _, metric in kept] == [2], kept
    assert len(engine()._options_matching_range("insumos que vencen entre 2 y 6 meses", scored())) == 3


def test_dominated_option_is_not_offered():
    # Nueva: «visitas domiciliarias del tablero gestión»: VISITAS DOMICILIARIAS
    # explica todo; VISITAS solo una parte.
    scored = [(1.0, _by_id("visitas")), (1.0, _by_id("visitas_dom"))]
    kept = engine()._drop_dominated_options("cuantas visitas domiciliarias hubo", scored)
    assert [metric["metric_id"] for _, metric in kept] == ["visitas_dom"], kept
    # Si ambas explican lo mismo, se ofrecen las dos.
    same = engine()._drop_dominated_options("cuantas visitas hubo", scored)
    assert len(same) == 2, same


# ------------------------------------------------------------ 3. datos ↔ RAG
def test_process_questions_are_descriptive():
    # Nuevas: etapas / pasos / flujo de un proceso.
    for question in ("por que etapas pasa una remision", "que pasos tiene una solicitud de cama",
                     "cual es el flujo de una devolucion de farmacia"):
        assert descriptive_phrase(question), question
    for question in ("cuantos pedidos hay por estado", "pedidos en cada etapa hoy"):
        assert not descriptive_phrase(question), question


# ------------------------------------------------------------ 4. agrupación por descripción
FIELDS = [
    _field("VISITAS", "RANGO_ESPERA", ["rango espera"]),
    _field("VISITAS", "MOTIVO_COD", ["motivo cod"]),
    _field("VISITAS", "SERVICIO", ["servicio"]),
]


def test_group_by_documented_description():
    # Nuevas: «visitas por rango de horas», «por qué causas se anularon visitas»,
    # «visitas según los motivos».
    qpb = builder()
    cases = {"rango de horas": "RANGO_ESPERA", "que causas se anularon": "MOTIVO_COD",
             "motivos": "MOTIVO_COD", "razones de anulacion": "MOTIVO_COD"}
    for tail, column in cases.items():
        field = qpb._group_field_in(tail, FIELDS)
        assert field is not None and field["column"] == column, (tail, field)


def test_group_by_alias_still_wins_and_unknown_tail_is_none():
    qpb = builder()
    assert qpb._group_field_in("servicio", FIELDS)["column"] == "SERVICIO"
    assert qpb._group_field_in("aseguradora", FIELDS) is None


# ------------------------------------------------------------ 5. cobertura del periodo
def test_upcoming_tables_do_not_cover_a_past_period():
    # Nuevas fuentes: «Citas asignadas para los próximos días», «una fila por cita ambulatoria próxima».
    for text in ("Citas asignadas para los próximos días con tipo y fecha.",
                 "Granularidad: una fila por cita ambulatoria próxima (CITA).",
                 "Cirugías programadas a futuro."):
        window = coverage_window(text, TODAY)
        assert window is not None and not covers(window, *LAST_MONTH, TODAY), (text, window)
        assert covers(window, TODAY, date(2026, 11, 7), TODAY), text
    # «la fecha de la próxima cita» no dice nada de la ventana de la tabla.
    assert coverage_window("Pacientes con la fecha de la próxima cita.", TODAY) is None


def test_table_inherits_the_window_of_its_origin():
    qpb = builder()
    assert qpb._metric_misses_period(_by_id("prog"), *LAST_MONTH) == "PROGRAMADAS"
    assert qpb._metric_misses_period(_by_id("prog"), TODAY, date(2026, 11, 7)) is None


def test_today_on_a_previous_day_cut_answers_the_cut():
    qpb = builder()
    today = {"start": TODAY.isoformat(), "end": date(2026, 10, 31).isoformat()}
    assert qpb._daily_cut_for_today(today, _by_id("visitas")) == "VISITAS"
    month = {"start": date(2026, 10, 1).isoformat(), "end": date(2026, 11, 1).isoformat()}
    assert qpb._daily_cut_for_today(month, _by_id("visitas")) is None
    assert qpb._daily_cut_for_today(today, _by_id("peso")) is None


# ------------------------------------------------------------ 6. familia de valores
def test_word_shared_by_several_values_filters_by_all():
    # Nueva: «visitas pediátricas» con URGENCIA PEDIATRICA, CONSULTA PEDIATRICA y
    # HOSPITALIZACION PEDIATRICA (la palabra no es el comienzo de los valores).
    qpb = builder()
    values = ["URGENCIA PEDIATRICA", "CONSULTA PEDIATRICA", "HOSPITALIZACION PEDIATRICA",
              "URGENCIA ADULTOS", "CONSULTA ADULTOS"]
    tied = values[:3]
    family = qpb._value_word_family("pediatricas", tied, values, "visitas pediatricas")
    assert family and family["values"] == sorted(tied), family
    # «no pediátricas» no es la familia; una palabra de todo el dominio tampoco.
    assert qpb._value_word_family("pediatricas", tied, values, "visitas no pediatricas") is None
    assert qpb._value_word_family("urgencia", ["URGENCIA A", "URGENCIA B"], ["URGENCIA A", "URGENCIA B"]) is None


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
