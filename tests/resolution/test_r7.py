"""
Ronda r7 (banco de desarrollo 96 %, holdout 76 %): reglas GENERALES, cada una
validada con preguntas NUEVAS (no del holdout ni del banco de desarrollo) sobre
un catálogo mínimo offline («Tablero Tiempos Porteria», «Tablero Gestion» y
«Tablero Aseguradoras»).

  1. «cuántos X» nombra «CANTIDAD DE X» / «NÚMERO DE X» completo (TU04: CANTIDAD
     DE TRIAGES del TABLERO TIEMPOS URGENCIAS); «Total X» no se recorta.
  2. El tablero del indicador explica un calificativo («en urgencias» para un
     indicador del TABLERO TIEMPOS URGENCIAS), como ya lo hacía el puntaje.
  3. Un conteo implícito de un identificador («Recuento de PACNUMDOC») nunca le
     gana a un indicador cuyo propio nombre dice la entidad de la pregunta,
     aunque su página («TRIAGES ATENDIDOS») o su filtro coincidan.

Ejecutar:  python -m tests.resolution.test_r7
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
from src.semantic.query_plan_builder import QueryPlanBuilder, canonical_token  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from tests.resolution.test_resolution import _source  # noqa: E402

POR = "Tablero Tiempos Porteria"
GES = "Tablero Gestion"
ASE = "Tablero Aseguradoras"
TODAY = date(2026, 11, 3)


def _metric(metric_id, label, model, table, column, dax, pages, aggregation="DistinctCount"):
    return {
        "metric_id": metric_id, "label": label, "measure": None, "aliases": [label],
        "source_type": "visual_aggregation", "semantic_model": model, "report": model, "reports": [model],
        "table": table, "column": column, "aggregation": aggregation, "dax_expression": dax,
        "validation_status": "approved",
        "appearances": [{"report": model, "page_display_name": page, "page_name": page,
                         "visual_id": f"v_{metric_id}_{index}", "visual_title": None, "visual_type": "card"}
                        for index, page in enumerate(pages)],
    }


METRICS = [
    _metric("cant_visitas", "CANTIDAD DE VISITAS", POR, "OPORTUNIDAD_VISITA", "OID_VISITA",
            "DISTINCTCOUNT('OPORTUNIDAD_VISITA'[OID_VISITA])", ["TIEMPO VISITA"]),
    _metric("tiempo_visita", "TIEMPO PARA VISITA", POR, "OPORTUNIDAD_VISITA", "MIN",
            "AVERAGE('OPORTUNIDAD_VISITA'[MIN])", ["TIEMPO VISITA"], "Average"),
    _metric("visitas", "VISITAS", GES, "VISITAS_G", "OID", "DISTINCTCOUNT('VISITAS_G'[OID])", ["CONSOLIDADO"]),
    _metric("recuento_doc", "Recuento de PACNUMDOC", ASE, "PACIENTES_PORTERIA", "PACNUMDOC",
            "COUNT('PACIENTES_PORTERIA'[PACNUMDOC])", ["VISITAS ATENDIDAS PORTERIA"], "Count"),
    _metric("total_pedidos", "TOTAL PEDIDOS", GES, "PEDIDOS", "OID", "COUNT('PEDIDOS'[OID])", ["PEDIDOS"], "Count"),
]


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    sources = [_source("por", POR, POR, ["tablero tiempos porteria"]), _source("ges", GES, GES, ["tablero gestion"]),
               _source("ase", ASE, ASE, ["tablero aseguradoras"])]
    files = {
        catalog / "source_registry.json": {
            "models": [{"semantic_model": s["semantic_model"], "semantic_model_key": s["source_group"],
                        "technical_catalog": s["technical_catalog"]} for s in sources],
            "sources": sources},
        rag / "visual_metrics_catalog.json": {"schema_version": 2, "reports": []},
        rag / "master_metrics.json": {"metrics": METRICS},
    }
    for source in sources:
        files[catalog / f"{source['source_group']}_rag.json"] = {
            "semantic_model": source["semantic_model"], "relationships": [], "tables": []}
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


def _by_id(metric_id):
    return next(metric for metric in METRICS if metric["metric_id"] == metric_id)


def _resolve(question):
    qpb = builder()
    return qpb._resolve_metric(question, qpb._source_context(question))


# ------------------------------------------------------------ 1. «cuántos X» = «CANTIDAD DE X»
def test_count_question_names_cantidad_de_x():
    qpb = builder()
    weights = qpb._token_weight_index()
    # Nuevas: «cuántas visitas van», «número de visitas de septiembre».
    for question in ("cuantas visitas van", "numero de visitas de septiembre"):
        assert qpb._core_name_score(question, "CANTIDAD DE VISITAS", weights) > qpb.min_metric_score, question
    # Sin conteo en la pregunta no se recorta («visitas por servicio»), ni «Total X».
    assert qpb._core_name_score("visitas por servicio", "CANTIDAD DE VISITAS", weights) == 0.0
    assert qpb._core_name_score("cuantos pedidos hay", "TOTAL PEDIDOS", weights) == 0.0
    # Una unidad genérica no nombra un indicador: «cuántos pacientes por aseguradora».
    assert qpb._core_name_score("cuantos pacientes hay por aseguradora", "CANTIDAD DE PACIENTES", weights) == 0.0
    assert qpb._core_name_score("cuantos usuarios van", "NUMERO DE USUARIOS", weights) == 0.0


def test_board_word_picks_the_count_of_that_board():
    # TU04 con preguntas nuevas: «en porteria» lo dice el tablero de CANTIDAD DE
    # VISITAS; VISITAS (de otro tablero) no lo explica.
    for question in ("cuantas visitas se han hecho este mes en porteria",
                     "cuantas visitas llevamos en porteria",
                     "cuantas visitas hubo en septiembre en porteria"):
        result = _resolve(question)
        top = result.get("metric") or (result.get("candidates") or [{}])[0].get("metric") or {}
        assert top.get("metric_id") == "cant_visitas", (question, result.get("status"), top.get("label"))


def test_board_tokens_explain_qualifiers():
    qpb = builder()
    tokens = qpb._board_tokens(_by_id("cant_visitas"))
    assert canonical_token("porteria") in tokens and "tablero" not in tokens, tokens


# ------------------------------------------------------------ 3. conteo implícito de identificador
def test_implicit_identifier_count_detection():
    qpb = builder()
    assert qpb._implicit_identifier_count(_by_id("recuento_doc"))
    assert qpb._implicit_identifier_count({"label": "Conteo de OID_TRIAGE1", "column": "OID_TRIAGE1"})
    assert qpb._implicit_identifier_count({"label": "Recuento de NUMERO_DOCUMENTO"})
    assert not qpb._implicit_identifier_count(_by_id("cant_visitas"))           # nombre de negocio
    assert not qpb._implicit_identifier_count({"label": "Recuento de SERVICIO", "column": "SERVICIO"})


def test_implicit_count_goes_behind_named_qualifier_candidates():
    # Nueva: «cuántas visitas atendidas en porteria»: «Recuento de PACNUMDOC» de
    # la página VISITAS ATENDIDAS PORTERIA cubre las palabras por su página, pero
    # CANTIDAD DE VISITAS las dice en su nombre y su tablero.
    qpb = builder()
    question = "cuantas visitas atendidas en porteria"
    found = qpb._qualifier_candidates(question, qpb._source_context(question),
                                      [canonical_token("porteria")], [canonical_token("visitas")])
    ids = [item["metric"]["metric_id"] for item in found]
    assert "recuento_doc" not in ids[:1], ids


def test_dominated_options_drop_implicit_identifier_count():
    # Nuevas: opciones «Recuento de PACNUMDOC» y CANTIDAD DE VISITAS que
    # explican lo mismo -> queda la de nombre de negocio.
    qpb = builder()
    engine = QueryEngine.__new__(QueryEngine)
    engine.query_plan_builder = qpb
    engine._trace = None
    engine._think = lambda *args, **kwargs: None
    saved = qpb.__dict__.get("question_coverage")
    qpb.question_coverage = lambda question, metric: (None, {"visita", "porteria"})
    try:
        for question in ("cuantas visitas van en porteria", "numero de visitas de porteria hoy"):
            scored = [(1.0, _by_id("recuento_doc")), (1.0, _by_id("cant_visitas"))]
            kept = engine._drop_dominated_options(question, scored)
            assert [metric["metric_id"] for _, metric in kept] == ["cant_visitas"], kept
        # Sin otra opción con nombre de negocio, el conteo implícito se queda.
        scored = [(1.0, _by_id("recuento_doc")), (1.0, {"metric_id": "x", "label": "Recuento de OID"})]
        assert len(engine._drop_dominated_options("cuantas visitas", scored)) == 2
    finally:
        if saved is None:
            qpb.__dict__.pop("question_coverage", None)
        else:
            qpb.question_coverage = saved


# ------------------------------------------------------------ 4. familia por coincidencia aproximada (H05)
_PATCHED = ("_implicit_eligible", "_field_filters_metric", "_value_token_index", "_get_values", "_prefetch_next",
            "_spurious_value_reason", "_value_contradiction", "_generic_partial_value")


def _with_domain(qpb, values):
    from src.semantic.query_plan_builder import canonical_tokens
    saved = {name: qpb.__dict__.get(name) for name in _PATCHED}
    qpb._implicit_eligible = lambda field, model: True
    qpb._field_filters_metric = lambda metric, field: True
    qpb._value_token_index = lambda model, field: [(value, canonical_tokens(value)) for value in values]
    qpb._get_values = lambda model, table, column, limit=None: list(values)
    qpb._prefetch_next = lambda *args, **kwargs: None
    qpb._spurious_value_reason = lambda *args, **kwargs: None
    qpb._value_contradiction = lambda *args, **kwargs: False
    qpb._generic_partial_value = lambda *args, **kwargs: False
    return saved


def _fuzzy(qpb, words):
    field = {"table": "PEDIDOS", "column": "TIPO", "kind": "column", "aliases": ["TIPO"]}
    return qpb._fuzzy_qualifier_filters(_by_id("visitas"), [field], set(), words, question=" ".join(words))


def test_fuzzy_word_common_to_several_values_filters_by_all():
    qpb = builder()
    saved = _with_domain(qpb, ["URGENTE INTERNO", "URGENTE EXTERNO", "NORMAL", "DEVOLUCION"])
    try:
        # Nuevas: «pedidos urgentes», «urgentes» (plural: coincidencia aproximada).
        for words in (["urgentes"], ["urgentes", "pedidos"]):
            found = _fuzzy(qpb, words)
            assert found, words
            resolved = found[0][1]
            assert resolved["value"] is None and resolved["values"] == [
                "URGENTE EXTERNO", "URGENTE INTERNO"], (words, resolved)
        # La palabra que distingue («internos») elige uno solo.
        found = _fuzzy(qpb, ["urgentes", "internos"])
        assert found and found[0][1]["value"] == "URGENTE INTERNO", found
        # Una palabra de un solo valor sigue eligiendo ese valor.
        found = _fuzzy(qpb, ["devoluciones"])
        assert found and found[0][1]["value"] == "DEVOLUCION", found
    finally:
        _restore(qpb, saved)


# ------------------------------------------------------------ 5. «por día de la semana» (H09)
def test_day_of_week_is_a_category_not_daily_granularity():
    from src.semantic.period_parser import PeriodParser
    parser = PeriodParser(today=TODAY)
    # Nuevas: «pedidos por día de la semana», «visitas por dia de semana en mayo».
    for text in ("pedidos por dia de la semana", "visitas por dia de semana en mayo"):
        assert parser.granularity(text) is None, (text, parser.granularity(text))
    # «por día» y «por semana» siguen siendo granularidad.
    assert parser.granularity("visitas por dia en mayo")["unit"] == "day"
    assert parser.granularity("pedidos por semana")["unit"] == "week"


def test_group_label_skips_implicit_aggregation_reference():
    # «Primera fecha: DIA_SEMANA» (referencia nativa del visual) no es el
    # encabezado; nuevas columnas: TURNO_LLEGADA, DIA_SEMANA.
    qpb = builder()
    for column in ("DIA_SEMANA", "TURNO_LLEGADA"):
        field = {"semantic_model": GES, "table": "T", "column": column,
                 "aliases": [f"Primera fecha: {column}", column, f"T.{column}"]}
        label = qpb._group_label(field, _by_id("visitas"))
        assert ":" not in label, label


# ------------------------------------------------------------ 6. verbo de reparto (H02)
def test_distribution_verb_is_not_the_head_noun():
    from src.semantic.query_plan_builder import canonical_phrases
    # Nuevas: «cómo están distribuidas las visitas por servicio», «cómo se
    # reparten los pedidos x tipo», «cómo quedaron divididos los kilos por turno».
    for text, kept in (("como estan distribuidas las visitas por servicio", "visitas por servicio"),
                       ("como se reparten los pedidos x tipo", "pedidos x tipo"),
                       ("como quedaron divididos los kilos por turno", "kilos por turno")):
        rewritten, changes = canonical_phrases(text)
        assert changes and kept in rewritten, (text, rewritten)
        assert not any(word in rewritten for word in ("distribuid", "reparten", "dividid")), rewritten
    # Sin «por <X>» no se toca («visitas repartidas» puede ser un estado).
    assert canonical_phrases("cuantas visitas repartidas hay")[1] == []
    # Con el verbo quitado, el sustantivo principal es lo que se reparte.
    qpb = builder()
    question = canonical_phrases("como estan distribuidas las visitas por servicio")[0]
    assert qpb._head_token(question, qpb._source_context(question)) == canonical_token("visitas")


def _restore(qpb, saved):
    for name, value in saved.items():
        if value is None:
            qpb.__dict__.pop(name, None)
        else:
            qpb.__dict__[name] = value


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
