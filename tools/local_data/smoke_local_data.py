"""
Comprobación rápida de que un data/ reconstruido arranca los componentes de
app.build_system() que no necesitan Power BI ni Ollama:
HybridRetriever (Qdrant), SourceModelRouter, MasterMetricResolver y
QueryPlanBuilder (con un proveedor Power BI de mentira que no ejecuta DAX).

Uso:
    python -m tools.local_data.smoke_local_data [--data-root RUTA/data]
"""
import argparse
import contextlib
import io
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[2]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from tools.local_data.build_local_data import main_repository_root  # noqa: E402


QUESTIONS = [
    "¿Cuántos triages hubo en 2025?",
    "porcentaje de inasistencia de citas por especialidad",
    "¿cuántas cirugías se realizaron este año?",
    "total de consultas prioritarias",
    "pacientes pendientes",
    "dosis de antibióticos suministradas",
    "peso de ropa de lavandería por servicio",
    "ocupación de camas por servicio",
    "solicitudes pendientes de recepción técnica",
    "tiempos de dispensación de farmacia",
]


class OfflinePowerBIProvider:
    """Sustituto mínimo: no hay Power BI, ninguna consulta DAX se ejecuta."""

    default_semantic_model = None
    endpoint = None

    def execute_dax(self, dax=None, semantic_model=None, **kwargs):
        return {
            "status": "error",
            "error_type": "OfflineProvider",
            "error": "Power BI no disponible en la verificación local.",
            "rows": [],
            "columns": [],
        }

    def connect(self):
        return {"status": "offline"}

    def close(self):
        pass


def _quiet(func, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args, **kwargs)


def run(data_root, questions=QUESTIONS):
    from src.rag.retriever import HybridRetriever
    from src.semantic.source_model_router import SourceModelRouter
    from src.semantic.master_metric_resolver import MasterMetricResolver
    from src.semantic.query_plan_builder import QueryPlanBuilder

    project_root = data_root.parent
    provider = OfflinePowerBIProvider()

    retriever = _quiet(HybridRetriever, data_root / "vector_db" / "qdrant")
    router = SourceModelRouter(
        source_registry_path=data_root / "catalog" / "source_registry.json",
        visual_catalog_path=data_root / "rag" / "visual_metrics_catalog.json",
        project_root=project_root,
        default_semantic_model=None,
    )
    resolver = MasterMetricResolver(data_root / "rag" / "master_metrics.json")
    builder = QueryPlanBuilder(
        master_metrics_path=data_root / "rag" / "master_metrics.json",
        visual_catalog_path=data_root / "rag" / "visual_metrics_catalog.json",
        source_router=router,
        powerbi_provider=provider,
        project_root=project_root,
    )

    print("Colección Qdrant:", retriever.collection_name)
    print("Modelos en el router:", len(router.semantic_models()))

    results = []
    for question in questions:
        hits = _quiet(retriever.search, question, limit=3)
        route = _quiet(router.resolve, question=question)
        metric = _quiet(resolver.resolve, question)
        plan = _quiet(builder.build, question)

        plan_metric = (plan.get("metric") or {}) if isinstance(plan, dict) else {}
        candidates = (
            (plan.get("metric_resolution") or {}).get("candidates") or []
            if isinstance(plan, dict) else []
        )
        results.append({
            "question": question,
            "rag_top": [
                (
                    round(hit.get("score", 0), 3),
                    hit.get("chunk_type") or (hit.get("payload") or {}).get("chunk_type"),
                    hit.get("dashboard") or (hit.get("payload") or {}).get("dashboard"),
                )
                for hit in (hits or [])[:3]
            ],
            "route": (route or {}).get("status"),
            "route_model": (route or {}).get("semantic_model"),
            "master_metric": (metric or {}).get("status"),
            "plan_status": plan.get("status") if isinstance(plan, dict) else None,
            "plan_metric": plan_metric.get("label"),
            "plan_model": plan_metric.get("semantic_model"),
            "plan_candidates": [
                (
                    (item.get("metric") or item).get("label"),
                    (item.get("metric") or item).get("semantic_model"),
                )
                for item in candidates[:4]
            ],
        })

    retriever.close()
    return results


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=main_repository_root() / "data")
    args = parser.parse_args(argv)

    for item in run(args.data_root.resolve()):
        print("\nP:", item["question"])
        print("  RAG:", item["rag_top"])
        print("  Router:", item["route"], "->", item["route_model"])
        print("  MasterMetricResolver:", item["master_metric"])
        print(
            "  Plan:", item["plan_status"], "->", item["plan_metric"],
            f"({item['plan_model']})" if item["plan_model"] else "",
        )
        if item["plan_candidates"]:
            print("  Candidatos:", item["plan_candidates"])


if __name__ == "__main__":
    main()
