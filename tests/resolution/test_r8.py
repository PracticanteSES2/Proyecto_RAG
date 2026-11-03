"""
Ronda r8: regresión AI04 («cuántos triages hubo en 2025»).

r7 hizo que «cuántos X» nombrara CANTIDAD DE X (TU04). Con eso CANTIDAD DE
TRIAGES (TIEMPOS URGENCIAS) empata por puntaje con TRIAGES (Demanda
Insatisfecha) y la resolución queda «ambigua» entre esos dos: se perdía la
contrapregunta de homónimos «existe en varios tableros», que también ofrece
TOTAL_TRIAGES (ATENCIONES INSTITUCIONALES, el total institucional).

Regla general: un empate entre indicadores que son el MISMO concepto con otro
nombre técnico (misma `_name_key`: X, CANTIDAD DE X, TOTAL_X) se resuelve con
la regla de homónimos (`_same_name_ambiguity`): todas las fuentes, con su
filtro de cobertura del periodo. Si la pregunta nombra algo que solo explica
uno (el tablero «en porteria»), no cambia nada.

Validado con preguntas NUEVAS sobre un catálogo mínimo offline (VISITAS en
tres tableros): año completo y mes en curso, con y sin servicio.

Ejecutar:  python -m tests.resolution.test_r8
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

from src.semantic.query_plan_builder import QueryPlanBuilder  # noqa: E402
from src.semantic.source_model_router import SourceModelRouter  # noqa: E402
from tests.resolution.test_resolution import _source  # noqa: E402

POR = "Tablero Tiempos Porteria"
GES = "Tablero Gestion"
INS = "Tablero Institucional"
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
    _metric("visitas", "VISITAS", GES, "VISITAS_G", "OID", "DISTINCTCOUNT('VISITAS_G'[OID])", ["CONSOLIDADO"]),
    _metric("cant_visitas", "CANTIDAD DE VISITAS", POR, "OPORTUNIDAD_VISITA", "OID_VISITA",
            "DISTINCTCOUNT('OPORTUNIDAD_VISITA'[OID_VISITA])", ["TIEMPO VISITA"]),
    _metric("total_visitas", "TOTAL_VISITAS", INS, "VISITAS_I", "OID",
            "DISTINCTCOUNT('VISITAS_I'[OID])", ["RESUMEN"]),
    _metric("tiempo_visita", "TIEMPO PARA VISITA", POR, "OPORTUNIDAD_VISITA", "MIN",
            "AVERAGE('OPORTUNIDAD_VISITA'[MIN])", ["TIEMPO VISITA"], "Average"),
]


def _build_fixture(root):
    catalog, rag = root / "data" / "catalog", root / "data" / "rag"
    catalog.mkdir(parents=True)
    rag.mkdir(parents=True)
    sources = [_source("por", POR, POR, ["tablero tiempos porteria"]), _source("ges", GES, GES, ["tablero gestion"]),
               _source("ins", INS, INS, ["tablero institucional"])]
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


def _ids(plan):
    resolution = plan.get("metric_resolution") or {}
    if resolution.get("metric") and plan.get("status") != "ambiguous":
        return [resolution["metric"].get("metric_id")]
    return [item["metric"].get("metric_id") for item in resolution.get("candidates") or []]


class _AllAnswer:
    """El catálogo offline no trae tablas con fecha: ningún homónimo armaría
    un plan «listo» con periodo y `_homonyms_that_answer` (regla previa, no la
    de r8) los descartaría a todos. Aquí se asume que todos responden."""

    def __enter__(self):
        self.qpb = builder()
        self.saved = self.qpb.__dict__.get("_homonyms_that_answer")
        self.qpb._homonyms_that_answer = lambda *args, **kwargs: None
        return self.qpb

    def __exit__(self, *exc):
        if self.saved is None:
            self.qpb.__dict__.pop("_homonyms_that_answer", None)
        else:
            self.qpb._homonyms_that_answer = self.saved
        return False


def _tie(*metric_ids, scores=(1.40, 1.37)):
    by_id = {metric["metric_id"]: metric for metric in METRICS}
    return {"status": "ambiguous", "candidates": [
        {"metric": by_id[metric_id], "score": score, "business_score": score, "matched_name": by_id[metric_id]["label"]}
        for metric_id, score in zip(metric_ids, scores)
    ]}


# ------------------------------------------------------------ 1. empate de homónimos
def test_homonym_tie_offers_every_board():
    # Nuevas, sin servicio: año completo, año pasado y mes en curso. El empate
    # VISITAS / CANTIDAD DE VISITAS no deja fuera a TOTAL_VISITAS.
    with _AllAnswer() as qpb:
        for question in ("cuantas visitas hubo en 2025", "cuantas visitas hubo el año pasado",
                         "cuantas visitas van este mes"):
            plan = qpb._homonym_tie_ambiguity(question, qpb._source_context(question), _tie("visitas", "cant_visitas"))
            assert plan is not None, question
            assert plan.get("reason") == "same_name_in_several_boards", (question, plan.get("reason"))
            assert set(_ids(plan)) == {"visitas", "cant_visitas", "total_visitas"}, (question, _ids(plan))


def test_tie_between_different_concepts_is_untouched():
    # VISITAS frente a TIEMPO PARA VISITA no son el mismo concepto.
    qpb = builder()
    question = "cuantas visitas hubo en 2025"
    tie = _tie("visitas", "tiempo_visita")
    assert qpb._homonym_tie_ambiguity(question, qpb._source_context(question), tie) is None
    # Un candidato lejos del primero (fuera del margen) no cuenta como empate.
    far = _tie("visitas", "cant_visitas", scores=(1.40, 0.60))
    assert qpb._homonym_tie_ambiguity(question, qpb._source_context(question), far) is None


def test_build_without_service_asks_among_all_homonyms():
    with _AllAnswer() as qpb:
        for question in ("cuantas visitas hubo en 2025", "cuantas visitas van este mes"):
            plan = qpb.build(question)
            ids = _ids(plan)
            assert plan.get("status") == "ambiguous", (question, plan.get("status"), ids)
            assert set(ids) == {"visitas", "cant_visitas", "total_visitas"}, (question, ids)


def test_build_with_service_keeps_the_board_count():
    # TU04 con preguntas nuevas: «en porteria» lo dice solo el tablero de
    # CANTIDAD DE VISITAS; la regla de homónimos no lo vuelve a abrir.
    with _AllAnswer() as qpb:
        for question in ("cuantas visitas se han hecho este mes en porteria",
                         "cuantas visitas hubo en 2025 en porteria"):
            plan = qpb.build(question)
            ids = _ids(plan)
            assert ids and ids[0] == "cant_visitas", (question, plan.get("status"), ids)
            assert "total_visitas" not in ids, (question, ids)


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
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
